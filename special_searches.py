import datetime
import time
from aqt import mw

def get_notes_added_on_day_of_year(day_of_year : int, limit: int):
    
    day_now = datetime.datetime.now().timetuple().tm_yday
    # nid_now = int(time.time()* 1000)
    # nid_then = nid_now - (day_now - day_of_year) * (24 * 60 * 60 * 1000)
    date_now = datetime.datetime.utcnow() 
    date_year_begin = datetime.datetime(year=date_now.year, month=1, day=1, hour=0 ,minute=0)    
    date_then = date_year_begin + datetime.timedelta(day_of_year)
    nid_midnight = int(date_then.timestamp() * 1000)
    nid_next_midnight = nid_midnight + 24 * 60 * 60 * 1000
    res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where nid > %s and nid < %s order by nid asc" % (nid_midnight, nid_next_midnight)).fetchall()
    return to_print_list(res)


def get_cal_info_context(day_of_year : int):
    date_now = datetime.datetime.utcnow() 
    oneday = 24 * 60 * 60 * 1000
    date_year_begin = datetime.datetime(year=date_now.year, month=1, day=1, hour=0 ,minute=0)    
    date_then = date_year_begin + datetime.timedelta(day_of_year)
    nid_midnight = int(date_then.timestamp() * 1000)
    date_then_str = time.strftime('%a, %d %B, %Y', time.localtime((nid_midnight + 1000) / 1000))
    nid_midnight_three_days_before = nid_midnight - 3 * oneday
    nid_midnight_three_days_after = nid_midnight + 4 * oneday
    res = mw.col.db.execute("select distinct notes.id from notes where id > %s and id < %s order by id asc" % (nid_midnight_three_days_before, nid_midnight_three_days_after)).fetchall()
    context = [0, 0, 0, 0, 0, 0, 0]
    for nid in res:
        context[int((nid[0] - nid_midnight_three_days_before) / oneday)] += 1
    html_content = ""
    for i, cnt in enumerate(context):
        if cnt > 20:
            color = "cal-three"
        elif cnt > 10:
            color = "cal-two"
        elif cnt > 0:
            color = "cal-one"
        else: 
            color = ""
        html_content += """<div class='cal-block-week %s %s' data-index='%s' onclick='pycmd("calInfo %s")'>%s</div>""" % (color, "cal-lg" if i == 3 else "", day_of_year - (3 - i),day_of_year - (3 - i), cnt)
    html = """
    
    <div style='text-align: center; margin-bottom: 4px;'>
        <span>%s</span> 
    </div>
    <div style='width: 100%%; text-align: center;'>%s</div>""" % (date_then_str, html_content)    


    return html


def getCreatedSameDay(searchIndex, editor, nid):
    stamp = searchIndex.output.getMiliSecStamp()
    searchIndex.output.latest = stamp
    searchIndex.lastSearch = (nid, None, "createdSameDay")
    try:
        nidMinusOneDay = nid - (24 * 60 * 60 * 1000)
        nidPlusOneDay = nid + (24 * 60 * 60 * 1000)

        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where nid > %s and nid < %s order by nid desc" %(nidMinusOneDay, nidPlusOneDay)).fetchall()

        dayOfNote = int(time.strftime("%d", time.localtime(nid/1000)))
        rList = []
        c = 0
        for r in res:
            dayCreated = int(time.strftime("%d", time.localtime(int(r[0])/1000)))
            if dayCreated != dayOfNote:
                continue
            if not str(r[0]) in searchIndex.pinned:
                rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
                c += 1
                if c >= searchIndex.limit:
                    break
        if editor.web is not None:
            if len(rList) > 0:
                searchIndex.output.printSearchResults(rList, stamp, editor)
            else:
                editor.web.eval("setSearchResults(``, 'No results found.')")
    except:
        if editor.web is not None:
            editor.web.eval("setSearchResults('', 'Error in calculation.')")

def getRandomNotes(searchIndex, decks):
    if searchIndex is None:
        return
    stamp = searchIndex.output.getMiliSecStamp()
    searchIndex.output.latest = stamp
    searchIndex.lastSearch = (None, decks, "random")

    if not "-1" in decks:
        deckQ =  "(%s)" % ",".join(decks)
    else:
        deckQ = ""

    limit = searchIndex.limit
    if deckQ:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where did in %s order by random() limit %s" % (deckQ, limit)).fetchall()
    else:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid order by random() limit %s" % limit).fetchall()
    rList = []
    for r in res:
        rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return { "result" : rList, "stamp" : stamp }


def getCreatedNotesOrderedByDate(searchIndex, editor, decks, limit, sortOrder):
    stamp = searchIndex.output.getMiliSecStamp()
    searchIndex.output.latest = stamp
    if sortOrder == "desc":
        searchIndex.lastSearch = (None, decks, "lastCreated", limit)
    else:
        searchIndex.lastSearch = (None, decks, "firstCreated", limit)

    if not "-1" in decks and len(decks) > 0:
        deckQ =  "(%s)" % ",".join(decks)
    else:
        deckQ = ""
    if len(deckQ) > 0:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where did in %s order by nid %s limit %s" %(deckQ, sortOrder, limit)).fetchall()
    else:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid order by nid %s limit %s" % (sortOrder, limit)).fetchall()
    rList = []
    for r in res:
        #pinned items should not appear in the results
        if not str(r[0]) in searchIndex.pinned:
            rList.append((r[1], r[2], r[3], r[0], 1, r[4]))

    if editor.web is not None:
        if len(rList) > 0:
            searchIndex.output.printSearchResults(rList, stamp, editor)
        else:
            editor.web.eval("setSearchResults(``, 'No results found.')")


def getLastReviewed(decks, limit):
    if decks is not None and len(decks) > 0 and not "-1" in decks:
        deckQ = "(%s)" % ",".join(decks)
    else:
        deckQ = ""

    if deckQ:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.id as rid from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, notes.mid from notes join cr on notes.id = cr.nid where cr.did in %s order by cr.rid desc limit %s" % (deckQ, limit)
    else:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.id as rid from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, notes.mid from notes join cr on notes.id = cr.nid order by cr.rid desc limit %s" % limit
    res = mw.col.db.execute(cmd).fetchall()
    rList = []
    for r in res:
        rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return rList

def getLastLapses(decks, limit):
    if decks is not None and len(decks) > 0 and not "-1" in decks:
        deckQ = "(%s)" % ",".join(decks)
    else:
        deckQ = ""

    if deckQ:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.id as rid, revlog.ease from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, notes.mid from notes join cr on notes.id = cr.nid where cr.ease = 1 and cr.did in %s order by cr.rid desc limit %s" % (deckQ, limit)
    else:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.id as rid, revlog.ease from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, notes.mid from notes join cr on notes.id = cr.nid where cr.ease = 1 order by cr.rid desc limit %s" % limit
    res = mw.col.db.execute(cmd).fetchall()
    rList = []
    for r in res:
        rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return rList

def getRandomUntagged(decks, limit):
    if not "-1" in decks:
        deckQ =  "(%s)" % ",".join(decks)
    else:
        deckQ = ""
    if deckQ:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where did in %s and (tags is null or tags = '') order by random() limit %s" % (deckQ, limit)).fetchall()
    else:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where tags is null or tags = '' order by random() limit %s" % limit).fetchall()
    rList = []
    for r in res:
        rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return rList
    

def findNotesWithLongestText(decks, limit, pinned):
    if not "-1" in decks and len(decks) > 0:
        deckQ =  "(%s)" % ",".join(decks)
    else:
        deckQ = ""
    if pinned is None:
        pinned = []
    if len(deckQ) > 0:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid where did in %s order by length(replace(trim(flds), '\u001f', '')) desc limit %s" %(deckQ, limit)).fetchall()
    else:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, mid from notes left join cards on notes.id = cards.nid order by length(replace(trim(flds), '\u001f', '')) desc limit %s" % (limit )).fetchall()
    rList = []
    for r in res:
        #pinned items should not appear in the results
        if not str(r[0]) in pinned:
            rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return rList

def getByTimeTaken(decks, limit, mode):
    if decks is not None and len(decks) > 0 and not "-1" in decks:
        deckQ = "(%s)" % ",".join(decks)
    else:
        deckQ = ""

    if deckQ:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.time, revlog.id as rid, revlog.ease from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, avg(cr.time) as timeavg from notes join cr on notes.id = cr.nid where cr.ease = 1 and cr.did in %s group by cr.nid order by timeavg %s limit %s" % (deckQ, mode, limit)
    else:
        cmd = "with cr as (select cards.nid, cards.id, cards.did, revlog.time, revlog.id as rid, revlog.ease from revlog join cards on cards.id = revlog.cid) select distinct notes.id, flds, tags, cr.did, avg(cr.time) as timeavg from notes join cr on notes.id = cr.nid where cr.ease = 1 group by cr.nid order by timeavg %s limit %s" % (mode, limit)
    res = mw.col.db.execute(cmd).fetchall()
    rList = []
    for r in res:
        rList.append((r[1], r[2], r[3], r[0], 1, r[4]))
    return rList

def getLastModifiedNotes(searchIndex, editor, decks, limit):
    stamp = searchIndex.output.getMiliSecStamp()
    searchIndex.output.latest = stamp
    searchIndex.lastSearch = (None, decks, "lastModified")

    if not "-1" in decks and len(decks) > 0:
        deckQ =  "(%s)" % ",".join(decks)
    else:
        deckQ = ""
    if len(deckQ) > 0:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, notes.mid, notes.mod from notes left join cards on notes.id = cards.nid where did in %s order by notes.mod desc limit %s" %(deckQ, limit)).fetchall()
    else:
        res = mw.col.db.execute("select distinct notes.id, flds, tags, did, notes.mid, notes.mod from notes left join cards on notes.id = cards.nid order by notes.mod desc limit %s" % (limit)).fetchall()
    rList = []
    for r in res:
        if not str(r[0]) in searchIndex.pinned:
            rList.append((r[1], r[2], r[3], r[0], 1, r[4]))

    if editor.web is not None:
        if len(rList) > 0:
            searchIndex.output.printSearchResults(rList, stamp, editor)
        else:
            editor.web.eval("setSearchResults(``, 'No results found.')")


def _find_cards_with_one_more_rep(cid: int):
    reps = mw.col.db.execute("select count(*) from revlog where (type = 1 or type = 2) and cid = %s" % cid).fetchone()[0]

    cards_ivls = []
    others = {}

    query = "select ro.id, ro.cid, ro.ease, ro.ivl, ro.factor, ro.time, ro.type from revlog ro join (select cid, count(*) from revlog where type = 1 or type = 2 group by cid having count(*) > %s or cid = %s) ri on ro.cid = ri.cid where type = 1 or type = 2" % (reps, cid)

    res = mw.col.db.execute(query).fetchall()

    for r in res:
        if r[1] == cid:
            cards_ivls.append(r[3])
        else:
            if not r[1] in others:
                others[r[1]] = []
            if len(others[r[1]]) < reps + 1:
                others[r[1]].append([r[3], r[5], r[2], r[6]])

    #find most similar
    similarities = []
    
    if cards_ivls:
        ivl_one_percent = sum(cards_ivls) / 100.0
    else:
        ivl_one_percent = 1

    for cid, rev_list in others.items():
        
        ivl_diff = 0.0
        ivl_diff_in_percent_total = 0.0
        times_diff = 0.0
        pass_rate_sum = 0.0
        
        for i, rev_list_item in enumerate(rev_list):
            if i < len(rev_list) - 1:
                c_ivl = _to_day_ivl(rev_list_item[0])
                card_ivl = _to_day_ivl(cards_ivls[i])
                ivl_diff += abs(c_ivl - card_ivl)
                pass_rate_sum += (1 if rev_list_item[2] != 1 else 0) 
            else:
                ivl_diff_in_percent_total = round(ivl_diff / ivl_one_percent, 1)
                ivl_diff_in_percent_avg = round(ivl_diff_in_percent_total / (len(rev_list) - 1), 1)
                ivl_at_current_step = _to_day_ivl(rev_list[-2][0])
                avg_pass_rate = 100 * pass_rate_sum / (len(rev_list) - 1)

                similarities.append([ivl_diff, cid, rev_list_item, ivl_diff_in_percent_total, ivl_diff_in_percent_avg, ivl_at_current_step, avg_pass_rate, rev_list])                
    similarities = sorted(similarities, key=lambda x: x[4])

    return [cards_ivls, similarities]



def find_similar_cards(cid : int, min_similarity: int, limit : int):
    loaded = _find_cards_with_one_more_rep(cid)
    similarities = loaded[1]
    avg_similarity = 0.0
    ivl_diff_in_percent_avg_sum = 0.0

    next_success_sum = 0.0
    current_ivl_sum = 0.0
    pass_rate_sum = 0.0

    avg_next_success_chance_up_to_now = 0.0
    avg_current_ivl_up_to_now = 0.0
    avg_pass_rate_up_to_now = 0.0

    revlists = []

    for i, s in enumerate(similarities):
        
        ivl_diff_in_percent_avg_sum += s[4]
        avg_similarity = 100.0 - ivl_diff_in_percent_avg_sum / (i + 1)

        if i > limit or avg_similarity < min_similarity and current_ivl_sum != 0.0:
            res = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i,
                                                "revlists" : revlists
            }
            html = _build_similar_cards_subpage(res)
            return [res, html]

        current_ivl_sum += _to_day_ivl(s[5])
        avg_current_ivl_up_to_now = current_ivl_sum / (i + 1)

        next_success_sum += (1 if s[2][2]  != 1 else 0)
        avg_next_success_chance_up_to_now = 100 * next_success_sum / (i + 1)

        pass_rate_sum += s[6]
        avg_pass_rate_up_to_now = pass_rate_sum / (i + 1)

        revlists.append(s[7])

    return None

def _build_similar_cards_subpage(res):
    html = """
    <table class="striped full-width" >
        <tr>
            <td>Est. Success Chance (Next Review)</td>
            <td>%s</td>
        </tr>
        <tr>
            <td>Avg. Interval at Cards Current Step</td>
            <td>%s</td>
        </tr>
        <tr>
            <td>Sample Size</td>
            <td>%s</td>
        </tr>
    </table>
    <br/><br/>


    """ % (res["avg_next_success_chance"],
    res["avg_current_ivl"],
    res["sample_size"]
    )

    rows = ""
    for i, revl in enumerate(res["revlists"]):
        rows += "<tr>" 
        for rev in revl:
            type = rev[3]
            ivl = rev[0]
            rows += "<td>%s</td>" % round(_to_day_ivl(ivl), 1)
        rows += "</tr>"
    
    html += """
    <table class='striped full-width'>
       %s 
    </table>
    """ % rows
    return html

def find_cards_with_similar_rep_history(cid : int):
    
    loaded = _find_cards_with_one_more_rep(cid)
    cards_ivls = loaded[0]
    similarities = loaded[1]


    avg_similarity = 0.0
    avg_similarity_steps_results = {}
    ivl_diff_in_percent_avg_sum = 0.0

    next_success_sum = 0.0
    current_ivl_sum = 0.0
    pass_rate_sum = 0.0

    avg_next_success_chance_up_to_now = 0.0
    avg_current_ivl_up_to_now = 0.0
    avg_pass_rate_up_to_now = 0.0

    for i, s in enumerate(similarities):
        ivl_diff_in_percent_avg_sum += s[4]
        avg_similarity = 100.0 - ivl_diff_in_percent_avg_sum / (i + 1)

        if avg_similarity < 90.0 and 90 not in avg_similarity_steps_results and current_ivl_sum != 0.0:
            avg_similarity_steps_results[90] = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i
            }
        if avg_similarity < 80.0 and 80 not in avg_similarity_steps_results and current_ivl_sum != 0.0:
            avg_similarity_steps_results[80] = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i
            }

        if avg_similarity < 70.0 and 70 not in avg_similarity_steps_results and current_ivl_sum != 0.0:
            avg_similarity_steps_results[70] = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i
            }
        
        if avg_similarity < 60.0 and 60 not in avg_similarity_steps_results and current_ivl_sum != 0.0:
            avg_similarity_steps_results[60] = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i
            }

        if avg_similarity < 50.0 and 50 not in avg_similarity_steps_results:
            avg_similarity_steps_results[50] = { "avg_next_success_chance" : avg_next_success_chance_up_to_now,
                                                "avg_current_ivl": avg_current_ivl_up_to_now,
                                                "avg_pass_rate" : avg_pass_rate_up_to_now,
                                                "sample_size" : i
            }
            break

        current_ivl_sum += _to_day_ivl(s[5])
        avg_current_ivl_up_to_now = current_ivl_sum / (i + 1)

        next_success_sum += (1 if s[2][2]  != 1 else 0)
        avg_next_success_chance_up_to_now = 100 * next_success_sum / (i + 1)

        pass_rate_sum += s[6]
        avg_pass_rate_up_to_now = pass_rate_sum / (i + 1)

    # successes = 0.0
    # counts = 0.0
    # for x in most_similar:
    #     if x[2][2] != 1:
    #         if x[0] > 0:
    #             successes += (1 / x[0]) 
    #         else:
    #             successes += (1 / 0.1) 
      
    #     if x[0] > 0:
    #         counts += (1 / x[0]) 
    #     else:
    #         counts += (1 / 0.1) 

    # success_rate = round((successes / counts) * 100, 1)

    return [avg_similarity_steps_results] 


def to_print_list(db_list):
    rList = []
    for r in db_list:
        rList.append((r[1], r[2], r[3], r[0]))
    return rList

def _to_day_ivl(ivl):
    if ivl < 0:
        return abs(ivl) / (24 * 60 * 60)
    return ivl
