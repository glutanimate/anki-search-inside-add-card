from aqt import mw
from aqt.qt import *
from anki.find import Finder
import aqt
import time
import os
from .state import checkIndex, get_index, set_index, set_corpus, get_corpus, corpus_is_loaded, get_edit
from .logging import *
from .web import loadSynonyms, showSearchResultArea, printStartingInfo
from .fts_index import FTSIndex
from .whoosh_index import WhooshSearchIndex

def get_notes_in_collection():  
    """
    Reads the collection and builds a list of tuples (note id, note fields as string, note tags, deck id, model id)
    """
    config = mw.addonManager.getConfig(__name__)
    deckList = config['decks']
    deckStr = ""
    for d in list(mw.col.decks.decks.values()):
        if d['name'] in deckList:
           deckStr += str(d['id']) + ","
    if len(deckStr) > 0:
        deckStr = "(%s)" %(deckStr[:-1])
    
    if deckStr:
        oList = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where did in %s" %(deckStr))
    else:
        oList = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid")
    uList = list()
    for id, flds, t, did, mid in oList:
        uList.append((id, flds, t, did, str(mid)))
    return uList

def build_index(force_rebuild = False, execute_after_end = None):
    config = mw.addonManager.getConfig(__name__)
    if get_index() is None:
        if not corpus_is_loaded():
            corpus = get_notes_in_collection()
            set_corpus(corpus)
        #check if we have to rebuild the index
        index_already_there = not force_rebuild and not _should_rebuild()
        #build index in background to prevent ui from freezing
        p = ProcessRunnable(_build_index, index_already_there)
        if execute_after_end is not None:
            p.after_end = execute_after_end
        p.start()

def _build_index(index_up_to_date):

    """
    Builds the index. Result is stored in global var searchIndex.
    The index.type is either "Whoosh"/"SQLite FTS3"/"SQLite FTS4"/"SQLite FTS5"
    """
    start = time.time()
    config = mw.addonManager.getConfig(__name__)
    try:
        useFTS = config['useFTS']    
    except KeyError:
        useFTS = False
    searchIndex = None
    corpus = get_corpus()
    #fts4 based sqlite reversed index
    if config["disableNonNativeSearching"] or useFTS:
        searchIndex = FTSIndex(corpus, config["disableNonNativeSearching"], index_up_to_date)
        end = time.time()
        initializationTime = round(end - start)
    #whoosh index
    else:
        searchIndex = WhooshSearchIndex(corpus, config["disableNonNativeSearching"], index_up_to_date)
        end = time.time()
        initializationTime = round(end - start)
        

    searchIndex.finder = Finder(mw.col)
    searchIndex.output.stopwords = searchIndex.stopWords
    searchIndex.output.fields_to_hide_in_results = config["fieldsToHideInResults"]
    searchIndex.selectedDecks = []
    searchIndex.lastSearch = None
    searchIndex.lastResDict = None
    searchIndex.tagSearch = True
    searchIndex.tagSelect = False
    searchIndex.topToggled = True
    searchIndex.output.edited = {}
    searchIndex.initializationTime = initializationTime
    searchIndex.synonyms = loadSynonyms()
    searchIndex.logging = config["logging"]
    try:
        limit = config['numberOfResults']
        if limit <= 0:
            limit = 1
        elif limit > 5000:
            limit = 5000
    except KeyError:
        limit = 500
    searchIndex.limit = limit

    try:
        showRetentionScores = config["showRetentionScores"]
    except KeyError:
        showRetentionScores = True
    searchIndex.output.showRetentionScores = showRetentionScores
    try:
        hideSidebar = config["hideSidebar"]
    except KeyError:
        hideSidebar = False
    searchIndex.output.hideSidebar = hideSidebar

    if searchIndex.logging:
        log("\n--------------------\nInitialized searchIndex:")
        log("""Type: %s\n# Stopwords: %s \n# Synonyms: %s \nLimit: %s \n""" % (searchIndex.type, len(searchIndex.stopWords), len(searchIndex.synonyms), limit))

    editor = aqt.mw.app.activeWindow().editor if hasattr(aqt.mw.app.activeWindow(), "editor") else None
    if editor is not None and editor.addMode:
        searchIndex.output.editor = editor
    set_index(searchIndex)
    editor = editor if editor is not None else get_edit()    
    showSearchResultArea(editor, initializationTime=initializationTime)
    printStartingInfo(editor)
    

def _should_rebuild():
    """
    Check if the index has to be rebuilt.
    """

    info = get_index_info()
    corpus = get_corpus() 
    config = mw.addonManager.getConfig(__name__)

    # if the index type changed, rebuild
    if (info["type"] == "Whoosh" and config["useFTS"]) or (info["type"] != "Whoosh" and not config["useFTS"]):
         return True

    # not used atm, so always false
    if info["shouldRebuild"]:
        toggle_should_rebuild()
        return True

    #if db file / index dir is not existing, rebuild
    if config["useFTS"]:
        file_path = os.path.dirname(os.path.realpath(__file__)).replace("\\", "/").replace("/indexing.py", "") + "/search-data.db"
        if not os.path.isfile(file_path):
            return True
    else:
        file_path = os.path.dirname(os.path.realpath(__file__)).replace("\\", "/").replace("/indexing.py", "") + "/index"
        if not os.path.exists(file_path):
            return True

    if info["size"] != len(corpus):
        return True

   

    
    if len(corpus) < config["alwaysRebuildIndexIfSmallerThan"]:
        return True 

    #if the decks used when building the index the last time differ from the decks used now, rebuild
    if len(config["decks"]) != len(info["decks"]):
        return True

    for d in config["decks"]:
        if d not in info["decks"]:
            return True
    

    #if the excluded fields when building the index the last time differ from the excluded fields now, rebuild
    if len(config["fieldsToExclude"]) != len(info["fieldsToExclude"]):
        return True

    for model_name, field_list in config["fieldsToExclude"].items():
        if model_name not in info["fieldsToExclude"]:
            return True
        if len(field_list) != len(info["fieldsToExclude"][model_name]):
            return True
            for field_name in field_list:
                if field_name not in info["fieldsToExclude"][model_name]:
                    return True
    
    if len(set(config["stopwords"])) != info["stopwordsSize"]:
        return True

    return False


class ProcessRunnable(QRunnable):
    """
    Only used to build the index in background atm.
    """
    def __init__(self, target, *args):
        QRunnable.__init__(self)
        self.t = target
        self.args = args
        self.after_end = None

    def run(self):
        self.t(*self.args)
        if self.after_end is not None:
            self.after_end()

    def start(self):
        QThreadPool.globalInstance().start(self)

