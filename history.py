# -*- coding: utf-8 -*-
# Kodi's own watched history of this add-on (its video database) to the server,
# as late reports: whatever the server knows that's newer wins. Started from the
# add-on settings, on the Kodi whose history counts (e.g. the main one).

import os
import re
import sqlite3
import time
from datetime import datetime
from urllib.parse import unquote

import xbmcvfs

from service import ADDON_ID, FILE_ID, is_ours, log, report


def newest_video_database():
    folder = xbmcvfs.translatePath('special://database')
    versions = [(int(m.group(1)), name) for name in os.listdir(folder)
                for m in [re.match(r'MyVideos(\d+)\.db$', name)] if m]
    return os.path.join(folder, max(versions)[1]) if versions else None


def to_ms(last_played):
    try:
        return int(time.mktime(datetime.strptime(last_played, '%Y-%m-%d %H:%M:%S').timetuple()) * 1000)
    except (TypeError, ValueError):
        return 1  # unknown: older than anything the server has


def read_history():
    """{file id: (play count, resume position, total time, last played in ms)} of this add-on's files."""
    database = newest_video_database()
    if database is None:
        return {}
    connection = sqlite3.connect('file:{0}?mode=ro'.format(database), uri=True)
    try:
        rows = connection.execute(
            'SELECT path.strPath, files.strFilename, files.playCount, files.lastPlayed,'
            ' bookmark.timeInSeconds, bookmark.totalTimeInSeconds'
            ' FROM files JOIN path ON path.idPath = files.idPath'
            ' LEFT JOIN bookmark ON bookmark.idFile = files.idFile AND bookmark.type = 1'
        ).fetchall()
    finally:
        connection.close()

    # the latest wins (a file can be there by plugin url and by stream url)
    history = {}
    for folder, filename, play_count, last_played, position, total in rows:
        url = unquote(unquote((folder or '') + (filename or '')))
        match = FILE_ID.search(url)
        if match is None or not (url.startswith('plugin://' + ADDON_ID) or is_ours(url)):
            continue
        if not play_count and not position:
            continue
        file_id = int(match.group(1))
        at = to_ms(last_played)
        if file_id not in history or history[file_id][3] < at:
            history[file_id] = (play_count or 0, position or 0, total or 0, at)
    return history


def send_history(history, on_progress=None):
    """
    How many files went through: stops at the first one that doesn't (server
    unreachable), or when on_progress(files done) returns False.
    """
    done = 0
    for file_id, (play_count, position, total, at) in history.items():
        if on_progress is not None and on_progress(done) is False:
            break
        sent = True
        if play_count > 0:
            sent = report(file_id, total, total, 'end', at)
        if sent and position > 0:
            # (also) a resume point, e.g. rewatching
            sent = report(file_id, position, total, 'stop', at)
        if not sent:
            break
        done += 1
    log('sent watched history of {0} of {1} files'.format(done, len(history)))
    return done
