# -*- coding: utf-8 -*-
# Module: default
# Based on Roman V. M. example plugin https://github.com/romanvm/plugin.video.example
# still draft, but it works!

#xbmc.log("router objAPIresponse " + json.dumps(objAPIresponse))
#xbmcgui.Dialog().ok("name", json.dumps(objAPIresponse))

#my_addon = xbmcaddon.Addon()
#my_setting = my_addon.getSetting('my_setting') # returns the string 'true' or 'false'
#my_addon.setSetting('my_setting', 'false')

import sys
from urllib.parse import urlencode, parse_qsl
import xbmcgui
import xbmcplugin
import xbmcaddon

import urllib.request
import simplejson as json
from io import StringIO
import gzip

# Get the plugin url in plugin:// notation.
_url = sys.argv[0]
# Get the plugin handle as an integer number.
_handle = int(sys.argv[1])

# todo - get from settings
#API_URL = "http://krk.sytes.net:8181/api"
#VIDEO_URL = "http://krk.sytes.net:8181"
#API_URL = xbmcplugin.getSetting(_handle, 'api_url') #if xbmcplugin.getSetting(_handle, 'api_url') else xbmc.getSetting("api_url")
my_addon = xbmcaddon.Addon()
API_URL = my_addon.getSetting('api_url') # returns the string 'true' or 'false'
VIDEO_URL = xbmcplugin.getSetting(_handle, 'video_url')

xbmcplugin.getSetting

def getHttpURL(url):

    request = urllib.request.Request(url)
    request.add_header('Accept-encoding', 'gzip')
    response = urllib.request.urlopen(request)

    if response.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(response.read())
        f = gzip.GzipFile(fileobj=buf)
        return f.read()

    return response.read()


def get_url(**kwargs):
    """
    Create a URL for calling the plugin recursively from the given set of keyword arguments.

    :param kwargs: "argument=value" pairs
    :type kwargs: dict
    :return: plugin call URL
    :rtype: str
    """
    return '{0}?{1}'.format(_url, urlencode(kwargs))


def list_APIresponse(objAPIresponse):

    #xbmcgui.Dialog().ok("ok", "listing api response")

    # Set plugin category. It is displayed in some skins as the name
    # of the current section.
    if 'category' in objAPIresponse:
        xbmcplugin.setPluginCategory(_handle, objAPIresponse['category'])

    # Set plugin content. It allows Kodi to select appropriate views
    # for this type of content.

    if 'content' in objAPIresponse:
        xbmcplugin.setContent(_handle, objAPIresponse['content'])


    # Get items
    if 'items' in objAPIresponse:
        items = objAPIresponse['items']

        # Iterate through items
        for item in items:

            # Create a list item with a text label and a thumbnail image.
            list_item = xbmcgui.ListItem(label=item['label'])

            # Set graphics (thumbnail, fanart, banner, poster, landscape etc.) for the list item.
            if 'thumb' in item:
                list_item.setArt({'thumb': item['thumb']})
            if 'icon' in item:
                list_item.setArt({'icon': item['icon']})
            if 'fanart' in item:
                list_item.setArt({'fanart': item['fanart']})

            # Set additional info for the list item.
            # https://codedocs.xyz/xbmc/xbmc/group__python__xbmcgui__listitem.html#ga0b71166869bda87ad744942888fb5f14
            # 'mediatype' is needed for a skin to display info for this ListItem correctly.


            if 'title' in item:
                list_item.setInfo('video', {'title': item['title']})

            if 'mediatype' in item:
                list_item.setInfo('video', {'mediatype': item['mediatype']})

            if 'size' in item: #long (1024) - size in bytes
                list_item.setInfo('video', {'size': item['size']})

            if 'duration' in item: # integer (245) - duration in seconds
                list_item.setInfo('video', {'duration': item['duration']})

            if 'aired' in item: # string (2008-12-07)
                list_item.setInfo('video', {'aired': item['aired']})

            if 'date' in item: # string (d.m.Y / 01.01.2009) - file date
                list_item.setInfo('video', {'date': item['date']})

            if 'plot' in item: # string (Long Description)
                list_item.setInfo('video', {'plot': item['plot']})

            if 'plotoutline' in item: # string (Short Description)
                list_item.setInfo('video', {'plotoutline': item['plotoutline']})


            # add properties - why it is not working?

            if 'IsPlayable' in item:
                if item['IsPlayable']:
                    list_item.setProperty('IsPlayable', 'true') # must be unicode or str, not bool
                    # list_item.setProperty('IsPlayable', item['IsPlayable']) - this doesn't work
                else:
                    list_item.setProperty('IsPlayable', 'false')


            # is_folder = True means that this item opens a sub-list of lower level items.
            if 'isFolder' in item:
                is_folder = item['isFolder']

            # Create a URL for a plugin recursive call.
            # Example: plugin://plugin.video.example/?action=query&path=epg

            # if path is available ->
            #   default action for folder is query,
            #   for file default is play, unless other action is provided
            #if path is not provided
            #   action is ignore

            if 'path' in item:
                if is_folder:
                    url = get_url(action='query', path=item['path'])
                else:
                    if 'action' in item:
                        if 'searchFor' in item:
                            url = get_url(action=item['action'], path=item['path'], searchFor=item['searchFor'])
                        else:
                            url = get_url(action=item['action'], path=item['path'])
                    else:
                        url = get_url(action='play', path=item['path'])
                        list_item.setProperty('IsPlayable', 'true')
            else:
                url = get_url(action='ignore')


            # add context menus (if there are any)

            if 'contextMenus' in item:
                contextMenus = item['contextMenus']
                listContextMenus = []

                # Iterate through contextMenus
                for contextMenu in contextMenus:

                    #should have a name (String) and urlParams (object)
                    params = contextMenu['urlParams']
                    cmUrl = '{0}?{1}'.format(_url, urlencode(params)) #context menu url
                    listContextMenus.append((contextMenu['name'], 'RunPlugin("' + cmUrl + '")'))

                if len(contextMenus) > 0:
                    list_item.addContextMenuItems(listContextMenus)

            # Add our item to the Kodi virtual folder listing.
            xbmcplugin.addDirectoryItem(_handle, url, list_item, is_folder)

    # Add a sort method for the virtual folder items
    if 'nosort' in objAPIresponse:
        xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_UNSORTED)
    else:
        #(alphabetically, ignore articles)
        xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
        xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_DATE)

    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(_handle)

def select_APIresponse(objAPIresponse):

    if 'items' in objAPIresponse:
        items = objAPIresponse['items']
        arrItems = [] #for now this is arr of strings

        # Iterate through items, collect all labels
        for item in items:

            arrItems.append(item['label'])

        #show the list
        dialog = xbmcgui.Dialog() #todo - let to choose own title
        selected = dialog.select('Select...', arrItems)
        #dialog.select('Choose a playlist', ['Playlist #1', 'Playlist #2', 'Playlist #3']) #list of strings / xbmcgui.ListItems - list of items shown in dialog.

        if selected == -1:
            pass
        else:
            #invoke self run on selected item
            strPath = items[selected]['path']
            url = get_url(action='query', path=strPath, selected=selected)
            #xbmcgui.Dialog().ok("running Container.Update", url)
            #xbmc.executebuiltin("Container.Update(" + url + ")")
            xbmc.executebuiltin('Container.Update(%s)' % url)


def play_video(path):
    """
    Play a video by the provided path.

    :param path: relative path or full path
    :type path: str
    """
    #xbmcgui.Dialog().ok("debug", "playvideo", path)

    if 'http' not in path:
        path = VIDEO_URL + path

    # Create a playable item with a path to play.
    play_item = xbmcgui.ListItem(path=path)
    # Pass the item to the Kodi player.
    xbmcplugin.setResolvedUrl(_handle, True, listitem=play_item)


def queryAPI(paramstring):

    strAPIresponse = getHttpURL(API_URL + "?" + paramstring)

    #parsed response from server
    objAPIresponse = json.loads(strAPIresponse)

    #show message if message is received
    if 'msgBoxOK' in objAPIresponse:
        xbmcgui.Dialog().ok("message from server", objAPIresponse['msgBoxOK'])

    if 'notification' in objAPIresponse:
        xbmc.executebuiltin('Notification("Notification from server!", "' + objAPIresponse['notification'] + '")')

    # to force the update the container (e.g. after file is deleted)
    # can have a replace (string) to reset the path history and must have urlParams (object)
    if 'forceUpdate' in objAPIresponse:
        forceUpdate = objAPIresponse['forceUpdate']

        if 'replace' in forceUpdate and 'urlParams' in forceUpdate:
            fuUrl = '{0}?{1}'.format(_url, urlencode(forceUpdate['urlParams'])) #forceUpdate url
            xbmc.executebuiltin("Container.Update(" + fuUrl + ", " + forceUpdate['replace'] + ")")
            return
        elif 'urlParams' in forceUpdate:
            fuUrl = '{0}?{1}'.format(_url, urlencode(forceUpdate['urlParams'])) #forceUpdate url
            xbmc.executebuiltin("Container.Update(" + fuUrl + ")")
            return

    #play video if play is received
    if 'play' in objAPIresponse:
        play_video(objAPIresponse['play'])

    #always update list, unless instructed otherwise
    if 'updateList' in objAPIresponse:
        if objAPIresponse['updateList']:
            list_APIresponse(objAPIresponse)
    else:
        list_APIresponse(objAPIresponse)

    #refresh container
    if 'refreshContainer' in objAPIresponse:
        if objAPIresponse['refreshContainer']:
            xbmc.executebuiltin("Container.Refresh")

    #show list to select
    if 'selectList' in objAPIresponse:
        if objAPIresponse['selectList']:
            #show a list of items to select
            select_APIresponse(objAPIresponse)

    #dialog.textviewer('Plot', 'Some movie plot.')

def router(paramstring):
    """
    Router function that calls other functions
    depending on the provided paramstring

    :param paramstring: URL encoded plugin paramstring
    :type paramstring: str
    """

    # Parse a URL-encoded paramstring to the dictionary of
    # {<parameter>: <value>} elements
    params = dict(parse_qsl(paramstring))
    # Check the parameters passed to the plugin

    if params:
        if params['action'] == 'query':
            # Query API server and generate list (or play video).
            queryAPI(paramstring)
        elif params['action'] == 'play':
            # Play a video from a provided URL.
            play_video(params['path'])
        elif params['action'] == 'ignore':
            # do nothing, this is info item
            strVariable = "nothing"
        elif params['action'] == 'search':
            # show search dialog for now, later will query the server
            dialog = xbmcgui.Dialog()
            if 'searchFor' in params:
                strSearchString = dialog.input("Search...", defaultt=params['searchFor'], type=xbmcgui.INPUT_ALPHANUM)
            else:
                strSearchString = dialog.input("Search...", type=xbmcgui.INPUT_ALPHANUM)
            if strSearchString:
                params['action'] = "query"
                params['search'] = strSearchString
                url = '{0}?{1}'.format(_url, urlencode(params))
                #xbmc.executebuiltin("Container.Update(" + url + ")")
                xbmc.executebuiltin('Container.Update(%s)' % url)
        else:
            # If the provided paramstring does not contain a supported action
            # we raise an exception. This helps to catch coding errors,
            # e.g. typos in action names.
            xbmcgui.Dialog().ok("Invalid paramstring:", paramstring)
            #raise ValueError('Invalid paramstring: {0}!'.format(paramstring))
    else:
        # If the plugin is called from Kodi UI without any parameters,
        # display the list of items
        queryAPI(paramstring)

if __name__ == '__main__':

    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    router(sys.argv[2][1:])
