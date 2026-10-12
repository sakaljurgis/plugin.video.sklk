# -*- coding: utf-8 -*-
# Background service: reports playback of this add-on's files to the server
# (POST <server>/api/state/<file id>), which keeps watched state and resume points
# for every app (e.g. the SKLK TV app); listings come back with that state.
#
# On its first start it also hands Kodi's own watched history of this add-on
# to the server, once (whatever the server knows that's newer wins).

import json
import os
import re
import sqlite3
import time
import urllib.request
from datetime import datetime
from urllib.parse import unquote

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = xbmcaddon.Addon().getAddonInfo('id')
FILE_ID = re.compile(r'all/play/(\d+)')
REPORT_EVERY = 30  # seconds, while playing
CLIENT = 'kodi'


def log(message, level=xbmc.LOGINFO):
    xbmc.log('[{0} service] {1}'.format(ADDON_ID, message), level)


def server_url():
    """The server setting (see main.py), read each time since it may change."""
    return re.sub(r'/api$', '', xbmcaddon.Addon().getSetting('api_url').strip().rstrip('/'))


def report(file_id, position, duration, event, at=None):
    """
    Positions in seconds; at (ms since epoch) only for late reports.
    True if the server got it (an answer that it doesn't know the file counts too).
    """
    if not server_url():
        return False
    payload = {'position': position, 'event': event, 'client': CLIENT}
    if duration:
        payload['duration'] = duration
    if at:
        payload['at'] = at
    request = urllib.request.Request(
        server_url() + '/api/state/' + str(file_id),
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': xbmcaddon.Addon().getSetting('auth_key')},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        return True
    except Exception as e:
        log('report failed: {0}'.format(e), xbmc.LOGWARNING)
        return False


def is_ours(url):
    """Streams of this add-on's server (as opposed to other add-ons, or LRT streams)."""
    server = server_url()
    return bool(server) and url.startswith(server + '/')


def refresh_if_ours():
    # e.g. Continue watching moves on to the next episode
    if xbmc.getInfoLabel('Container.FolderPath').startswith('plugin://' + ADDON_ID):
        xbmc.executebuiltin('Container.Refresh')


class Player(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.file_id = None
        self.position = 0
        self.duration = 0
        self.last_report = 0
        # (file_id, position, duration, event, at): retried until it goes through
        self.unsent = None

    def onAVStarted(self):
        self.finish('stop')  # in case another file was playing
        try:
            url = self.getPlayingFile()
        except RuntimeError:
            return
        match = FILE_ID.search(url) if is_ours(url) else None
        if match is None:
            return
        self.file_id = int(match.group(1))
        self.position = 0
        self.duration = 0
        self.update()
        self.send('start')

    def onPlayBackPaused(self):
        if self.file_id is not None:
            self.update()
            self.send('pause')

    def onPlayBackStopped(self):
        self.finish('stop')

    def onPlayBackEnded(self):
        self.finish('end')

    def onPlayBackError(self):
        self.finish('stop')

    def tick(self):
        """Every second, from the service loop."""
        if self.unsent and time.time() - self.last_report >= REPORT_EVERY:
            self.last_report = time.time()
            if report(*self.unsent):
                self.unsent = None

        if self.file_id is None:
            return
        self.update()
        if time.time() - self.last_report >= REPORT_EVERY and not xbmc.getCondVisibility('Player.Paused'):
            self.send('tick')

    def update(self):
        # after a stop there's no time to ask for, the last one known is reported
        try:
            if self.isPlayingVideo():
                self.position = self.getTime()
                self.duration = self.getTotalTime() or self.duration
        except RuntimeError:
            pass

    def finish(self, event):
        if self.file_id is None:
            return
        if event == 'end':
            self.position = self.duration
        self.send(event)
        self.file_id = None
        refresh_if_ours()

    def send(self, event):
        self.last_report = time.time()
        args = (self.file_id, self.position, self.duration, event)
        if report(*args):
            if self.unsent and self.unsent[0] == self.file_id:
                self.unsent = None
        else:
            self.unsent = args + (int(time.time() * 1000),)


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


def import_kodi_history():
    """
    Before this service, Kodi kept this add-on's watched state and resume points
    in its own database only. Send them to the server once, as late reports.
    """
    profile = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))
    marker = os.path.join(profile, 'history_imported')
    if os.path.exists(marker):
        return

    database = newest_video_database()
    rows = []
    if database:
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

    # by file id, the latest wins (a file can be there by plugin url and by stream url)
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

    for file_id, (play_count, position, total, at) in history.items():
        sent = True
        if play_count > 0:
            sent = report(file_id, total, total, 'end', at)
        if sent and position > 0:
            # (also) a resume point, e.g. rewatching
            sent = report(file_id, position, total, 'stop', at)
        if not sent:
            return  # server unreachable: try again next time

    if not os.path.isdir(profile):
        os.makedirs(profile)
    open(marker, 'w').close()
    log('imported watch history of {0} files'.format(len(history)))


def run():
    monitor = xbmc.Monitor()
    player = Player()
    try:
        import_kodi_history()
    except Exception as e:
        log('history import failed: {0}'.format(e), xbmc.LOGWARNING)

    while not monitor.waitForAbort(1):
        player.tick()


if __name__ == '__main__':
    run()
