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
    soundmonitor.py [-h] [--threshold=THRESH] [--emailto=EMAIL]
                    [--rate=RATE] [--seconds=SECONDS] [--server=SERVER]
                    [--warnperiod=PERIOD]

Options:
    -h                  Print this help message.
    --threshold=THRESH  Sound level alarm threhold, higher values are more
                        sensitive [default: 1000].
    --emailto=EMAIL     E-mail adress(es) to send a message to. If empty
                        no message is sent [default: scb@localhost].
    --server=SERVER     SMTP server [default: localhost].
    --rate=RATE         Audio data sampling rate [default: 44100].
    --seconds=SECONDS   Length of sound data to evaluate per scan [default: 1].
    --warnperiod=PERIOD Minimum duration between two alarm or warning
                        emails in seconds [default: 1800].
"""

import os
import numpy as np
from docopt import docopt
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import COMMASPACE
from email import encoders
import datetime
from collections import namedtuple

OPTS = namedtuple('OPTS', 'threshold rate seconds emailto server period')
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
        part.add_header('Content-Disposition', 'attachment',
                filename='{}'.format(os.path.basename(attachment)))
        msg.attach(part)
    smtp = smtplib.SMTP(message.server)
    smtp.sendmail(message.me, message.to, msg.as_string())
    smtp.close()
    print('email sent to {}, subject: {}'.format(msg['To'], msg['Subject']))


def getsoundlevel(opts):
    """Estimate sound level. Sound level is defined as mean absolute value
    of the microphone data."""
    record = 'arecord -q -t raw -f S16_LE -c 1\
            -r {rate} -d {seconds} foo.raw'.format(rate=opts.rate,
                    seconds=opts.seconds)
    if os.system(record) == 0:
        data = np.fromfile('foo.raw', dtype=np.int16, count=-1, sep='')
        data = data.astype(np.float32)
        meanabs = np.mean(np.abs(data))
    else:
        print("*** failed\n")
        meanabs = -1
    return meanabs


def recordday(opts, until):
    """Record sound level for one day, beginning and ending at 08:00h

    :until: @todo
    :returns: @todo

    """
    levels = np.array([])
    timestamps = np.array([], dtype='datetime64')
    plt.ion()
    lastwarningtime = (datetime.datetime.now() -
            datetime.timedelta(seconds=opts.period))
    lastalarmtime = lastwarningtime
    while datetime.datetime.now() < until:
        soundlevel = getsoundlevel(opts)
        levels = np.append(levels, soundlevel)
        timestamps = np.append(timestamps,
                np.datetime64(datetime.datetime.now()))
        plt.cla()
        plt.xlabel('sample number')
        plt.ylabel('Sound level')
        plt.plot([0, len(levels)],
                [opts.threshold * 0.9, opts.threshold * 1.1], 'w')
        plt.plot([0, len(levels)], [opts.threshold, opts.threshold], 'r')
        plt.plot(levels)
        plt.draw()
        if (soundlevel < 0) and (datetime.datetime.now() -
                lastwarningtime).total_seconds > opts.period:
            # Warning: recording has failed
            message = MESSAGE(
                    'compressor@localhost',
                    opts.emailto,
                    'Sound monitor warning',
                    'Warning: recording failed at {}'.format(
                        datetime.datetime.now().isoformat(' ')),
                    [], opts.server)
            sendemail(message)
            lastwarningtime = datetime.datetime.now()

        elif (0 < soundlevel < opts.threshold) and (datetime.datetime.now() -
                lastalarmtime).total_seconds() > opts.period:
            # Alarm: soundlevel below threshold
            message = MESSAGE(
                    'compressor@localhost',
                    opts.emailto,
                    '*** COMPRESSOR ALARM ***',
                    'ALARM! Sound level below threshold at {}'.format(
                        datetime.datetime.now().isoformat(' ')),
                    [],
                    opts.server)
            sendemail(message)
            lastalarmtime = datetime.datetime.now()
    filename = '{}_sound'.format(until.strftime('%Y-%m-%d'))
    fpt = file('{}.numpy'.format(filename), 'wb')
    np.save(fpt, timestamps)
    np.save(fpt, levels)
    plt.savefig('{}.png'.format(filename))
    os.system('arecord -q -f cd -d 5 {}.wav'.format(filename))
    message = MESSAGE(
            'compressor@localhost',
            opts.emailto,
            'Sound monitor daily message',
            'Sound monitor daily message: all in best order, have fun!',
            ['{}.png'.format(filename), '{}.wav'.format(filename)],
            'localhost')
    sendemail(message)


def main(options):
    """Main program..."""
    print(np.datetime64(datetime.datetime.now()))
    if type(options['--emailto']) == list:
        emailto = options['--emailto']
    else:
        emailto = [options['--emailto']]
    opts = OPTS(int(options['--threshold']), int(options['--rate']),
        float(options['--seconds']), emailto, options['--server'],
        int(options['--warnperiod']))
    message = MESSAGE(
            'compressor@localhost',
            opts.emailto,
            'Sound monitor started',
            'The sound monitor was started at {}'.format(
                datetime.datetime.now().isoformat(' ')),
            [],
            opts.server)
    sendemail(message)
    while 1:
        #todaymidnight = datetime.datetime.combine(datetime.date.today(),
        #        datetime.time())
        #until = todaymidnight + datetime.timedelta(days=1, hours=8)
        until = datetime.datetime.now() + datetime.timedelta(minutes=1)
        recordday(opts, until)


if __name__ == "__main__":
    ARGUMENTS = docopt(__doc__)
    print(ARGUMENTS)
    main(ARGUMENTS)
