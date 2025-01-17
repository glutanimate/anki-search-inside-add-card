import sqlite3
import os
import sys
import struct
import re
import time
import math
from aqt import *
from aqt.utils import showInfo, tooltip
from .output import *
import collections
from .textutils import *
from .logging import log, persist_index_info

class FTSIndex:

    def __init__(self, corpus, searchingDisabled, index_up_to_date):

        self.limit = 20
        self.pinned = []
        self.highlighting = True
        self.searchWhileTyping = True
        self.searchOnSelection = True
        self.dir = os.path.dirname(os.path.realpath(__file__)).replace("\\", "/").replace("/db.py", "")
        self.stopWords = []
        # mid : [fld_ord]
        self.fields_to_exclude = {}
        # stores values useful to determine whether the index has to be rebuilt on restart or not
        self.creation_info = {}
        self.threadPool = QThreadPool()
        self.output = Output()

        config = mw.addonManager.getConfig(__name__)
        try:
            self.stopWords = set(config['stopwords'])
        except KeyError:
            self.stopWords = []
        self.creation_info["stopwords_size"] = len(self.stopWords)
        self.creation_info["decks"] = config["decks"]
        #exclude fields
        try:
            self.fields_to_exclude = config['fieldsToExclude']
            self.creation_info["fields_to_exclude_original"] = self.fields_to_exclude 
        except KeyError:
            self.fields_to_exclude = {} 
        self.output.fields_to_exclude = self.fields_to_exclude

        #if fts5 is compiled, use it
        self.type = self._checkIfFTS5Available(config["logging"])
        self.creation_info["index_was_rebuilt"] = not index_up_to_date
        if not searchingDisabled and not index_up_to_date:
            cleaned = self._cleanText(corpus)
            try:
                os.remove(self.dir + "/search-data.db")
            except OSError:
                pass
            conn = sqlite3.connect(self.dir + "/search-data.db")
            conn.execute("drop table if exists notes")
            if self.type == "SQLite FTS5":
                conn.execute("create virtual table notes using fts5(nid, text, tags, did, source, mid)")
            elif self.type == "SQLite FTS4":
                conn.execute("create virtual table notes using fts4(nid, text, tags, did, source, mid)")
            else:
                conn.execute("create virtual table notes using fts3(nid, text, tags, did, source, mid)")
            
            conn.executemany('INSERT INTO notes VALUES (?,?,?,?,?,?)', cleaned)
            conn.execute("INSERT INTO notes(notes) VALUES('optimize')")
            conn.commit()
            conn.close()
        if not index_up_to_date:
            persist_index_info(self)


    def _checkIfFTS5Available(self, logging):
        con = sqlite3.connect(':memory:')
        cur = con.cursor()
        cur.execute('pragma compile_options;')
        available_pragmas = [s[0].lower() for s in cur.fetchall()]
        con.close()
        if logging:
            log("\nSQlite compile options: " + str(available_pragmas))
        if 'enable_fts5' in available_pragmas:
            return "SQLite FTS5"
        if 'enable_fts4' in available_pragmas:
            return "SQLite FTS4"
        if 'enable_fts3' in available_pragmas:
            return "SQLite FTS3"
        return "SQLite - No FTS detected (trying to use FTS3)"
   

    def _cleanText(self, corpus):
        filtered = list()
        text = ""
        for row in corpus:
            #if the notes model id is in our filter dict, that means we want to exclude some field(s)
            text = row[1]
            if row[4] in self.fields_to_exclude:
                text = remove_fields(text, self.fields_to_exclude[row[4]])
            text = clean(text, self.stopWords)
            filtered.append((row[0], text, row[2], row[3], row[1], row[4]))
        return filtered

    def removeStopwords(self, text):
        cleaned = ""
        for token in text.split(" "):
            if token.lower() not in self.stopWords:
                cleaned += token + " "
        if len(cleaned) > 0:
            return cleaned[:-1]
        return ""


    def search(self, text, decks):
        """
        Search for the given text.
        Args: 
        text - string to search, typically fields content
        decks - list of deck ids, if -1 is contained, all decks are searched
        """
        worker = Worker(self.searchProc, text, decks) 
        worker.stamp = self.output.getMiliSecStamp()
        self.output.latest = worker.stamp
        worker.signals.result.connect(self.printOutput)
        worker.signals.tooltip.connect(self.output.show_tooltip)
        self.threadPool.start(worker)


    def searchProc(self, text, decks):
        resDict = {}
        start = time.time()
        orig = text
        text = self.clean(text)
        resDict["time-stopwords"] = int((time.time() - start) * 1000)
        if self.logging:
            log("\nFTS index - Received query: " + text)
            log("Decks (arg): " + str(decks))
            log("Self.pinned: " + str(self.pinned))
            log("Self.limit: " +str(self.limit))
        self.lastSearch = (text, decks, "default")
        
        if len(text) == 0:
            self.output.editor.web.eval("setSearchResults(``, 'Query was empty after cleaning.<br/><br/><b>Query:</b> <i>%s</i>')" % trimIfLongerThan(orig, 100))
            if mw.addonManager.getConfig(__name__)["hideSidebar"]:
                return "Found 0 notes. Query was empty after cleaning."
            return
        start = time.time()
        text = expandBySynonyms(text, self.synonyms)
        resDict["time-synonyms"] = int((time.time() - start) * 1000)
        resDict["query"] = text
        if textTooSmall(text):
            if self.logging:
                log("Returning - Text was < 2 chars: " + text)
            return { "results" : [] }

        query = u" OR ".join(["tags:" + s.strip().replace("OR", "or") for s in text.split(" ") if not textTooSmall(s) ])
        if self.type == "SQLite FTS5":
            query += " OR " + " OR ".join(["text:" + s.strip().replace("OR", "or") for s in text.split(" ") if not textTooSmall(s) ]) 
        else:
            query += " OR " + " OR ".join([s.strip().replace("OR", "or") for s in text.split(" ") if not textTooSmall(s) ]) 
        if query == " OR ":
            if self.logging:
                log("Returning. Query was: " + query)
            return { "results" : [] }

        c = 0
        allDecks = "-1" in decks
        rList = list()
        conn = sqlite3.connect(self.dir + "/search-data.db")
        if self.type == "SQLite FTS5":
            dbStr = "select nid, text, tags, did, source, bm25(notes), mid from notes where notes match '%s' order by bm25(notes)" %(query)
        elif self.type == "SQLite FTS4":
            dbStr = "select nid, text, tags, did, source, matchinfo(notes, 'pcnalx'), mid from notes where text match '%s'" %(query)
        else:
            dbStr = "select nid, text, tags, did, source, matchinfo(notes), mid from notes where text match '%s'" %(query)

        try:
            start = time.time()
            res = conn.execute(dbStr).fetchall()
            resDict["time-query"] = int((time.time() - start) * 1000)
        except Exception as e:
            if self.logging:
                log("Executing db query threw exception: " + e.message)
            res = []
        if self.logging: 
            log("dbStr was: " + dbStr)
            log("Result length of db query: " + str(len(res)))


        resDict["highlighting"] = self.highlighting
        if self.type == "SQLite FTS5":
            for r in res:
                if not str(r[0]) in self.pinned and (allDecks or str(r[3]) in decks):
                    rList.append((r[4], r[2], r[3], r[0], r[5], r[6]))
                    c += 1
                    if c >= self.limit:
                        break

        elif self.type == "SQLite FTS4":
            start = time.time()
            for r in res:
                if not str(r[0]) in self.pinned and (allDecks or str(r[3]) in decks):
                    rList.append((r[4], r[2], r[3], r[0], self.bm25(r[5], 0, 1, 2, 0, 0), r[6]))
            resDict["time-ranking"] = int((time.time() - start) * 1000)
            
        else:
            start = time.time()
            for r in res:
                if not str(r[0]) in self.pinned and (allDecks or str(r[3]) in decks):
                    rList.append((r[4], r[2], r[3], r[0], self.simpleRank(r[5]), r[6]))
            resDict["time-ranking"] = int((time.time() - start) * 1000)
      
        conn.close()

        #if fts5 is not used, results are not sorted by score
        if not self.type == "SQLite FTS5":
            listSorted = sorted(rList, key=lambda x: x[4])
            rList = listSorted
        if self.logging:
            log("Query was: " + query)
            log("Result length (after removing pinned and unselected decks): " + str(len(rList)))
        resDict["results"] = rList[:min(self.limit, len(rList))]
        self.lastResDict = resDict
        return resDict

    def printOutput(self, result, stamp):
        query_set = None
        if self.highlighting and self.lastResDict is not None and "query" in self.lastResDict and self.lastResDict["query"] is not None:
            query_set =  set(replaceAccentsWithVowels(s).lower() for s in self.lastResDict["query"].split(" "))
        if type(result) is str:
            #self.output.show_tooltip(result)
            pass
        elif result is not None:
            self.output.printSearchResults(result["results"], stamp, logging = self.logging, printTimingInfo = True, query_set=query_set)
    
    
            
        



    def searchDB(self, text, decks):
        """
        Used for searches in the search mask,
        doesn't use the index, instead use the traditional anki search (which is more powerful for single keywords)
        """
        stamp = self.output.getMiliSecStamp()
        self.output.latest = stamp
        found = self.finder.findNotes(text)
        
        if len (found) > 0:
            if not "-1" in decks:
                deckQ =  "(%s)" % ",".join(decks)
            else:
                deckQ = ""
            #query db with found ids
            foundQ = "(%s)" % ",".join([str(f) for f in found])
            if deckQ:
                res = mw.col.db.execute("select distinct notes.id, flds, tags, did, notes.mid from notes left join cards on notes.id = cards.nid where nid in %s and did in %s" %(foundQ, deckQ)).fetchall()
            else:
                res = mw.col.db.execute("select distinct notes.id, flds, tags, did, notes.mid from notes left join cards on notes.id = cards.nid where nid in %s" %(foundQ)).fetchall()
            rList = []
            for r in res:
                #pinned items should not appear in the results
                if not str(r[0]) in self.pinned:
                    #todo: implement highlighting
                    rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
            return { "result" : rList[:self.limit], "stamp" : stamp }
        return { "result" : [], "stamp" : stamp }

    def _parseMatchInfo(self, buf):
        #something is off in the match info, sometimes tf for terms is > 0 when it should not be
        bufsize = len(buf)
        return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

    def clean(self, text):
        return clean(text, self.stopWords)


    
    def simpleRank(self, rawMatchInfo):
        """
        Based on https://github.com/saaj/sqlite-fts-python/blob/master/sqlitefts/ranking.py
        """
        match_info = self._parseMatchInfo(rawMatchInfo)
        score = 0.0
        p, c = match_info[:2]
        for phrase_num in range(p):
            phrase_info_idx = 2 + (phrase_num * c * 3)
            for col_num in range(c):
                col_idx = phrase_info_idx + (col_num * 3)
                x1, x2 = match_info[col_idx:col_idx + 2]
                if x1 > 0:
                    score += float(x1) / x2
        return -score

    

    def bm25(self, rawMatchInfo, *args):
        match_info = self._parseMatchInfo(rawMatchInfo)
        #increase?
        K = 0.5
        B = 0.75
        score = 0.0

        P_O, C_O, N_O, A_O = range(4)
        term_count = match_info[P_O]
        col_count = match_info[C_O]
        total_docs = match_info[N_O]
        L_O = A_O + col_count
        X_O = L_O + col_count

        if not args:
            weights = [1] * col_count
        else:
            weights = [0] * col_count
            for i, weight in enumerate(args):
                weights[i] = weight

        #collect number of different matched terms
        cd = 0
        for i in range(term_count):
            for j in range(col_count):
                x = X_O + (3 * j * (i + 1))
                if float(match_info[x]) != 0.0:
                    cd += 1 

        for i in range(term_count):
            for j in range(col_count):
                weight = weights[j]
                if weight == 0:
                    continue

                avg_length = float(match_info[A_O + j])
                doc_length = float(match_info[L_O + j])
                if avg_length == 0:
                    D = 0
                else:
                    D = 1 - B + (B * (doc_length / avg_length))

                x = X_O + (3 * j * (i + 1))
                term_frequency = float(match_info[x])
                docs_with_term = float(match_info[x + 2])

                idf = max(
                    math.log(
                        (total_docs - docs_with_term + 0.5) /
                        (docs_with_term + 0.5)),
                    0)
                denom = term_frequency + (K * D)
                if denom == 0:
                    rhs = 0
                else:
                    rhs = (term_frequency * (K + 1)) / denom

                score += (idf * rhs) * weight 
        return -score - cd * 20

    def deleteNote(self, nid):
        conn = sqlite3.connect(self.dir + "/search-data.db")
        conn.cursor().execute("DELETE FROM notes WHERE CAST(nid AS INTEGER) = %s;" % nid)
        conn.commit()
        conn.close()



    def addNote(self, note):
        content = " \u001f ".join(note.fields)
        tags = " ".join(note.tags)
        #did = note.model()['did']
        did = mw.col.db.execute("select distinct did from notes left join cards on notes.id = cards.nid where nid = %s" % note.id).fetchone()
        if did is None or len(did) == 0:
            return
        did = did[0]
        if str(note.mid) in self.fields_to_exclude:
            content = remove_fields(content, self.fields_to_exclude[str(note.mid)])
        conn = sqlite3.connect(self.dir + "/search-data.db")
        conn.cursor().execute("INSERT INTO notes (nid, text, tags, did, source, mid) VALUES (?, ?, ?, ?, ?, ?)", (note.id, clean(content, self.stopWords), tags, did, content, note.mid))
        conn.commit()
        conn.close()
        persist_index_info(self)

    def updateNote(self, note):
        self.deleteNote(note.id)
        self.addNote(note)

    def get_last_inserted_id(self):
        conn = sqlite3.connect(self.dir + "/search-data.db")
        row_id = conn.cursor().execute("SELECT id FROM notes_content ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        return row_id

    def get_number_of_notes(self):
        conn = sqlite3.connect(self.dir + "/search-data.db")
        res = conn.cursor().execute("select count(*) from notes_content").fetchone()[0]
        conn.close()
        return res


class Worker(QRunnable):
 
    def __init__(self, fn, *args):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        try:
            result = self.fn(*self.args)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            #use stamp to track time
            self.signals.result.emit(result, self.stamp)  
        finally:
            self.signals.finished.emit()

class WorkerSignals(QObject):
   
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object, object)
    progress = pyqtSignal(int)
    tooltip = pyqtSignal(str)
