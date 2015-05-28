#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2012-2014 Matt Martz
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from gevent import monkey
from gevent.pool import Pool
monkey.patch_all()

import os
import sys
import glob
import timeit
import argparse
import requests
import fileinput

this = os.path.abspath(__file__)
here = os.path.dirname(this)

parser = argparse.ArgumentParser()
parser.add_argument('url')
parser.add_argument('-c', '--count', type=int, default=8)
args = parser.parse_args()

r = requests.head(args.url)
content_length = int(r.headers.get('Content-Length', 0))
chunk_size = content_length / args.count
chunks = []
for i in xrange(args.count):
    if i == args.count - 1:
        boundary = (i + 1) * chunk_size
    else:
        boundary = ((i + 1) * chunk_size) - 1
    chunks.append((i * chunk_size, boundary))

filename = os.path.basename(args.url)
if os.path.isfile(filename):
    filename = '%s.0' % filename

globs = glob.glob(os.path.join(here, '%s.part*' % filename))
startcount = []
if len(globs) == args.count:
    sizes = []
    new_chunks = []
    for i, f in enumerate(globs):
        sizes.append(os.path.getsize(f))
        if (sizes[-1] != chunks[i][1] and
                sizes[-1] < chunks[i][1] - chunks[i][0]):
            new_chunks.append((
                chunks[i][0] + sizes[-1],
                ((i + 1) * chunk_size) - 1
            ))
            startcount.append(sizes[-1])
        else:
            print ('partial files already exist, and do not match the size '
                   'range')
            print '    %s' % '\n    '.join(globs)
            sys.exit(1)

    chunks[:] = new_chunks
    print ('partial files already exist and match count (%s). There is the '
           'posibility of creating a non working file. Please check hashes '
           'after download completion\n' % args.count)
elif globs:
    print ('partial files already exist, and do not match the count (%s) '
           'specified:' % args.count)
    print '    %s' % '\n    '.join(globs)
    sys.exit(1)

print 'Initializing download: %s' % args.url
print 'File size: %s bytes' % content_length
print 'Output file: %s' % filename
if startcount:
    print 'Resuming download\n'
else:
    print 'Starting download\n'


def getter(filename, chunk, bytecount):
    headers = {
        'Range': 'bytes=%s-%s' % chunk
    }
    r = requests.get(args.url, headers=headers, stream=True)
    with open(filename, 'a') as f:
        for block in r.iter_content(4096):
            if not block:
                break
            bytecount.append(len(block))
            f.write(block)
            f.flush()


files = []
bytecount = []
start = timeit.default_timer()
p = Pool(size=args.count)
for i, chunk in enumerate(chunks):
    files.append('%s.part%s' % (filename, i))
    p.spawn(getter, files[-1], chunk, bytecount)
while p.free_count() != p.size:
    p.join(timeout=0.1)
    total = float(sum(bytecount))
    if not total:
        continue
    speed = total/(timeit.default_timer() - start)
    remaining = content_length - total - sum(startcount)
    percent = ((total + sum(startcount)) / content_length) * 100
    sys.stdout.write('\r[%3.00f%%] %7.02f MB/s [%4.00fs] ' % (percent,
                                                              speed/1024**2,
                                                              remaining/speed))
    sys.stdout.flush()

print

with open(filename, 'w') as f:
    for block in fileinput.input(files, bufsize=4096):
        f.write(block)

for f in files:
    os.unlink(f)

print ('\nDownloaded %.00f MB in %.00f seconds. (%.02f MB/s)' %
       (content_length/1024**2, timeit.default_timer() - start, speed/1024**2))
