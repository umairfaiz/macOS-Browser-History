#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# Original Script:
#       OS X Auditor
# By:
#       Jean-Philippe Teissier ( @Jipe_ ) & al.
#  
#  This work is licensed under the GNU General Public License
#
#  Some Modifications To Date/Time by: jc@unternet.net
#  Modifications for Fidelis Endpoint: lucas@chumley.io

__description__ = 'Safari History Dumper, based on OS X Auditor'
__author__ = 'Lucas J. Chumley'
__version__ = '0.0.4'

ROOT_PATH = '/'
HOSTNAME = ''

import sys
reload(sys)
sys.setdefaultencoding('UTF8')

import optparse
import os
import hashlib
import logging
from logging.handlers import SysLogHandler
import sqlite3
import socket
import time
import json
import zipfile
import codecs                                                   #binary plist parsing does not work well in python3.3 so we are stuck in 2.7 for now
from functools import partial
import re
import bz2
import binascii
import platform
import gzip
import datetime


'''Deal with macOS's timestamping'''
TIMESTAMP_OFFSET = 978307200  # 31 years and almost an hour
# Actual time of visit to website: about 2017-03-17:20:26
# >>> datetime.datetime.fromtimestamp(511489553.667061)          
# datetime.datetime(1986, 3, 17, 19, 25, 53, 667061)
# >>> datetime.datetime.fromtimestamp(511489553.667061+978307200)
# datetime.datetime(2017, 3, 17, 20, 25, 53, 667061)
# The above machine was on Eastern Daylight time at the time. /jc@unternet.net

try:
    from urllib.request import urlopen                          #python3
except ImportError:
    import urllib, urllib2                                      #python2

try:
    import Foundation                                           #It only works on OS X
    FOUNDATION_IS_IMPORTED = True
#    print(u'DEBUG: Mac OS X Obj-C Foundation successfully imported')
except ImportError:
    print(u'DEBUG: Cannot import Mac OS X Obj-C Foundation. Installing PyObjC on OS X is highly recommended')
    try:
        import biplist
        BIPLIST_IS_IMPORTED = True
    except ImportError:
        print(u'DEBUG: Cannot import the biplist lib. Am I root? I may not be able to properly parse a binary pblist')
    try:
        import plistlib
        PLISTLIB_IS_IMPORTED = True
    except ImportError:
        print(u'DEBUG: Cannot import the plistlib lib. Am I root? I may not be able to properly parse a binary pblist')
        
def PrintAndLog(LogStr, TYPE):
    ''' Write a string of log depending of its type and call the function to generate the HTML log or the Syslog if needed '''

    global HTML_LOG_FILE
    global SYSLOG_SERVER

    if TYPE == 'INFO':# or 'INFO_RAW':  
        print(u'[INFO]^' + LogStr)
        logging.info(LogStr)
    else:
        print(TYPE + '^' + LogStr)
        logging.info(LogStr)
        
#    if TYPE == 'SAFARI':   #Adding in additional measures to tell where we found the entries. Also helps with debugging /ljc
#        print(u'[SAFARI]^' + LogStr)
#        logging.info(LogStr)
        
def read_sqlite(path, sql):
    '''
    return query result from SQLite3 database
    '''
    connection = sqlite3.connect(path)
    rows = connection.execute(sql)
    return rows
        
def ParseSafariProfile(User, Path):
    ''' Parse the different plist and SQLite databases in a Safari profile '''

    HistoryPlist = False
    DownloadsPlist = False
    NbFiles = 0

#    PrintAndLog(User + u'\'s Safari profile', 'SUBSECTION')

#    PrintAndLog(User + u'\'s Safari downloads', 'SUBSECTION')          # Maybe some day I can get the downloads parsing to work correctly. /ljc
#    DownloadsPlistPath = os.path.join(Path, 'Downloads.plist')
#    PrintAndLog(DownloadsPlistPath.decode('utf-8'), 'DEBUG')

#    DownloadsPlist = UniversalReadPlist(DownloadsPlistPath)

#    if DownloadsPlist:
#        if 'DownloadHistory' in DownloadsPlist:
#            Downloads = DownloadsPlist['DownloadHistory']
#            for DL in Downloads:
#                DlStr = u''
#                DlStr += DL['DownloadEntryURL'].decode('utf-8') + u' -> ' + DL['DownloadEntryPath'].decode('utf-8') + u' (' + DL['DownloadEntryIdentifier'].decode('utf-8') + u')\n'
#                PrintAndLog(DlStr, 'INFO')

#    PrintAndLog(User + u'\'s Safari history', 'SUBSECTION')
    if os.path.exists(os.path.join(Path, 'History.plist')):            #Legacy OS X plist type /ljc
        HistoryPlistPath = os.path.join(Path, 'History.plist')
#        PrintAndLog(HistoryPlistPath.decode('utf-8'), 'DEBUG')
        HistoryPlist = UniversalReadPlist(HistoryPlistPath)
        if HistoryPlist:
            if 'WebHistoryDates' in HistoryPlist:
                History =  HistoryPlist['WebHistoryDates']
                for H in History:
                    HStr = u''
                    if 'title' in H:
                        HStr += unicode(H['title']) + u' - '
                    if 'diplayTitle' in H:
                        HStr += unicode(H['diplayTitle']) + u' - '
                    elif 'displayTitle' in H:
                        HStr += unicode(H['displayTitle']) + u' - '
                    HStr += unicode(H['']) + u'\n'
                    PrintAndLog(HStr, 'INFO')
    elif os.path.exists(os.path.join(Path, 'History.db')):              #Added for FEP script being run on any Mac with macOS/X 10.10 or newer /ljc
        HistoryPlistPath = os.path.join(Path, 'History.db')
#        PrintAndLog(HistoryPlistPath.decode('utf-8'), 'DEBUG')
        visits = read_sqlite(HistoryPlistPath,
            'SELECT v.title, h.url, h.domain_expansion, v.visit_time'
            ' FROM history_items AS h, history_visits AS v'
            ' WHERE h.id=v.history_item')
        for visit in visits:

            timestamp = visit[-1] + TIMESTAMP_OFFSET
            visit_time = datetime.datetime.fromtimestamp(timestamp).strftime(
                '%Y-%m-%d:%H:%M:%S.') + str(timestamp).split('.')[1]
            visit = visit[:-1] + (visit_time,)
            PrintAndLog('^'.join(map(str, visit)), User)
            
def ParseSafari():
#    PrintAndLog(u'Users\' Safari profiles', 'SUBSECTION')
    for User in os.listdir(os.path.join(ROOT_PATH, 'Users')):
        UserSafariProfilePath = os.path.join(ROOT_PATH, 'Users', User, 'Library/Safari')
        if User[0] != '.' and os.path.isdir(UserSafariProfilePath):
            ParseSafariProfile(User, UserSafariProfilePath)
            
def ParseBrowsers():
    ''' If this script is ever expanded for FF or Chrome, their modules can be called here.   '''

#    PrintAndLog(u'Browsers', 'SECTION')

    ParseSafari()

def Main():
    ''' Here we go '''
    Parser = optparse.OptionParser(usage='usage: %prog [options]\n' + __description__ + ' v' + __version__, version='%prog ' + __version__)
    Parser.add_option('-b', '--browsers', action='store_true', default=False, help='Analyze browsers (Safari, FF & Chrome) ')

    (options, args) = Parser.parse_args()

    if sys.version_info < (2, 7) or sys.version_info > (3, 0):
        PrintAndLog(u'You must use python 2.7 or greater but not python 3', 'ERROR')                        # This error won't be logged
        exit(1)
        
    if options.browsers:
        ParseBrowsers()

if __name__ == '__main__':
    Main()