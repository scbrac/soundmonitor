#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Monitor the status of a helium compressor used within a MRI system. Read
the computer's microphone data, evaluate the sound level and send an e-mail if
the sound level falls below a threshold (i.e. compressor is off).

License:
    Copyright (C) 2014 Sönke Carstens-Behrens
    (carstens-behrens AT rheinahrcampus.de)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

Usage:
    soundmonitor.py (-h | --help)
    soundmonitor.py [-h] [--threshold=THRESH] [--emailto=EMAIL ...]
                    [--rate=RATE] [--seconds=SECONDS] [--server=SERVER]
                    [--warnperiod=PERIOD] [--aliveperiod=PERIOD] [--tmpdir=DIR]

Options:
    -h                   Print this help message.
    --threshold=THRESH   Sound level alarm threhold, higher values are more
                         sensitive [default: 1000].
    --emailto=EMAIL      E-mail adress(es) to send a message to. If empty
                         no message is sent [default: scb@localhost].
    --server=SERVER      SMTP server [default: localhost].
    --rate=RATE          Audio data sampling rate [default: 48000].
    --seconds=SECONDS    Length of sound data to evaluate per scan [default: 1]
    --warnperiod=PERIOD  Minimum duration between two alarm or warning
                         emails in seconds [default: 1800].
    --aliveperiod=PERIOD Duration between two sign of live emails, format:
                         nU, where n is an integer number an U is a unit (m for
                         minutes, d for days) [default: 1d]
    --tmpdir=DIR         Directory, e.g. ramdisk, where to save temporary data
                         (microphone sampling data) [default: /tmp]
"""

import os
import numpy as np
from docopt import docopt
import matplotlib
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import COMMASPACE
from email import encoders
import datetime
from collections import namedtuple

OPTS = namedtuple('OPTS', 'threshold rate seconds emailto server period\
        aliveperiod tmpdir')
MESSAGE = namedtuple('MESSAGE', 'me to subject text attachments server')


def sendemail(message):
    """Send an email, possibly with attachments.
    message is a namedtuple:
    .me          : email sender adress
    .to          : list of email recipients (if no recipient (empty list) is
                   given, no email will be sent)
    .subject     : email subject
    .text        : email text
    .attachments : list of file names to be attached (empty list for no
                   attachments)
    .server      : smpt server
    """
    if not message.to[0]:
        print('no recipient -> no email')
        return
    if message.attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(message.text))
    else:
        msg = MIMEText(message.text)
    msg['From'] = message.me
    msg['To'] = COMMASPACE.join(message.to)
    msg['Subject'] = message.subject
    for attachment in message.attachments:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(open(attachment, 'rb').read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition', 'attachment', filename='{}'.format(
                os.path.basename(attachment)))
        msg.attach(part)
    smtp = smtplib.SMTP(message.server)
    smtp.sendmail(message.me, message.to, msg.as_string())
    smtp.close()
    print('email sent to {}, subject: {}'.format(msg['To'], msg['Subject']))


def getsoundlevel(opts):
    """Estimate sound level. Sound level is defined as mean absolute value
    of the microphone data."""
    fixoptions = '-q -t raw -f S16_LE -c 1'
    record = 'arecord {fixoptions} -r {rate} -d {seconds} {filename}'.format(
        fixoptions=fixoptions,
        rate=opts.rate,
        seconds=opts.seconds,
        filename=os.path.join(opts.tmpdir, 'foo.raw'))
    if os.system(record) == 0:
        data = np.fromfile('{filename}'.format(
            filename=os.path.join(opts.tmpdir, 'foo.raw')), dtype=np.int16,
            count=-1, sep='')
        data = data.astype(np.float32)
        meanabs = np.mean(np.abs(data))
    else:
        print("*** failed\n")
        meanabs = -1
    return meanabs


def savesound(opts, minmax):
    """Save the sound files with minimum or maximum soundlevel per day."""
    copy = 'cp {fromfile} {tofile}'.format(
        fromfile=os.path.join(opts.tmpdir, 'foo.raw'),
        tofile='{date}_{minmax}'.format(
            date=datetime.datetime.now().strftime('%Y-%m-%d'),
            minmax=minmax))
    os.system(copy)


def latencyover(opts, lasttime):
    """Return true if latency is over, false otherwise. Latency is over if the
    time between lasttime and now is greater than the waiting time defined in
    opts.period."""
    if (datetime.datetime.now() - lasttime).total_seconds() > opts.period:
        return True
    else:
        return False


def getattachments(figure, timestamps, levels):
    """Save PNG file and WAV file to be attached to emails, return the file
    names as list."""
    filenamebase = '{}_sound'.format(
        datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
    pngfile = '{}.png'.format(filenamebase)
    # wavfile = '{}.wav'.format(filenamebase)
    # numpyfile = '{}.numpy'.format(filenamebase)
    # os.system('arecord -q -f cd -d 5 {}'.format(wavfile))
    figure.savefig(pngfile)
    # fpt = file(numpyfile, 'wb')
    # np.save(fpt, timestamps)
    # np.save(fpt, levels)
    # fpt.close()
    # return [pngfile, wavfile, numpyfile]
    return [pngfile]


def discharging():
    """Return true, if laptop battery is discharging, false otherwise."""
    bat0path = '/sys/class/power_supply/BAT0/uevent'
    bat1path = '/sys/class/power_supply/BAT1/uevent'
    if os.path.exists(bat0path):
        with open(bat0path) as fpt:
            lines = fpt.readlines()
    elif os.path.exists(bat1path):
        with open(bat1path) as fpt:
            lines = fpt.readlines()
    else:
        print('keine Batterie gefunden')
        return False  # no battery found
    batstatusline = [line for line in lines if 'POWER_SUPPLY_STATUS' in line]
    if 'discharging' in batstatusline[0].split('=')[1].lower():
        return True
    else:
        return False


def recordday(opts, until):
    """Record sound level until 'until'. If 'until' is measured in days,
    beginning and ending at 08:00h."""
    levels = []
    timestamps = []
    plt.close("all")
    plt.ion()
    fig, ax = plt.subplots()
    lastwarningtime = (datetime.datetime.now() -
                       datetime.timedelta(seconds=opts.period))
    lastalarmtime = lastwarningtime
    lastbatterytime = lastwarningtime
    minsoundlevel = 1e9
    maxsoundlevel = 0
    while datetime.datetime.now() < until:
        soundlevel = getsoundlevel(opts)
        levels.append(soundlevel)
        timestamps.append(matplotlib.dates.date2num(datetime.datetime.now()))
        ax.cla()
        ax.set_xlabel('sample number')
        ax.set_ylabel('Sound level')
        ax.plot_date(timestamps, levels, fmt='b-')
        ax.plot_date([timestamps[0], timestamps[-1]],
                     [opts.threshold * 0.9, opts.threshold * 1.1], 'w')
        ax.plot([timestamps[0], timestamps[-1]],
                [opts.threshold, opts.threshold], 'r')
        ax.xaxis.set_major_formatter(
            matplotlib.dates.DateFormatter('%H:%M:%S'))
        plt.draw()
        if (soundlevel < 0) and latencyover(opts, lastwarningtime):
            # Warning: recording has failed
            message = MESSAGE(
                'compressor@localhost',
                opts.emailto,
                'Sound monitor warning',
                'Warning: recording failed at {}'.format(
                    datetime.datetime.now().isoformat()),
                getattachments(plt, timestamps, levels), opts.server)
            sendemail(message)
            lastwarningtime = datetime.datetime.now()

        elif (0 < soundlevel < opts.threshold) and latencyover(opts,
                                                               lastalarmtime):
            # Alarm: soundlevel below threshold
            message = MESSAGE(
                'compressor@localhost',
                opts.emailto,
                '*** COMPRESSOR ALARM ***',
                'ALARM! Sound level below threshold at {}'.format(
                    datetime.datetime.now().isoformat()),
                getattachments(plt, timestamps, levels), opts.server)
            sendemail(message)
            lastalarmtime = datetime.datetime.now()
        if discharging() and latencyover(opts, lastbatterytime):
            # Warning: laptop runs on battery
            message = MESSAGE(
                'compressor@localhost',
                opts.emailto,
                'Warning: Sound monitor on battery',
                'Sound monitor laptops runs on battery at {}'.format(
                    datetime.datetime.now().isoformat()),
                getattachments(plt, timestamps, levels), opts.server)
            sendemail(message)
            lastbatterytime = datetime.datetime.now()
        if soundlevel < minsoundlevel:
            savesound(opts, 'min')
            minsoundlevel = soundlevel
        elif soundlevel > maxsoundlevel:
            savesound(opts, 'max')
            maxsoundlevel = soundlevel

    message = MESSAGE(
        'compressor@localhost',
        opts.emailto,
        'Sound monitor daily message',
        'Sound monitor daily message: all in best order, have fun!',
        getattachments(plt, timestamps, levels),
        opts.server)
    sendemail(message)


def main(options):
    """Main program..."""
    if type(options['--emailto']) == list:
        emailto = options['--emailto']
    else:
        emailto = [options['--emailto']]
    opts = OPTS(
        int(options['--threshold']), int(options['--rate']),
        float(options['--seconds']), emailto, options['--server'],
        int(options['--warnperiod']), options['--aliveperiod'],
        options['--tmpdir'])
    message = MESSAGE(
        'compressor@localhost',
        opts.emailto,
        'Sound monitor started',
        'The sound monitor was started at {}'.format(
            datetime.datetime.now().isoformat()),
        [],
        opts.server)
    sendemail(message)
    while 1:
        num = int(opts.aliveperiod[:-1])
        unit = opts.aliveperiod[-1]
        if unit == 'd':
            todaymidnight = datetime.datetime.combine(
                datetime.date.today(), datetime.time())
            until = todaymidnight + datetime.timedelta(days=num, hours=8)
        else:
            until = datetime.datetime.now() + datetime.timedelta(minutes=num)
        recordday(opts, until)


if __name__ == "__main__":
    ARGUMENTS = docopt(__doc__)
    print(ARGUMENTS)
    main(ARGUMENTS)
