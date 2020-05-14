import os
import sys
import time
import lorem
import logging
from functools import wraps
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from datetime import datetime

## Globals
MAX_DBCON_POOL = 4
MAX_WORDS_PER_ITER = 30

log = logging.getLogger('pgprof')

dbops = {'INSERT':'0', 'READ':'1', 'UPDATE':'2', 'DELETE':'3'}
opsdb = dict((v,k) for k,v in dbops.items())

## -------------------------------------------------------------------------- ##
def connect(dsn="PGDSN", numc=MAX_DBCON_POOL//2):
    """
    Connect to the database using an environment variable.
    """
    url = os.getenv(dsn)
    if not url:
        raise ValueError("no database url specified")

    minconns = numc
    maxconns = numc * 2
    return ThreadedConnectionPool(minconns, maxconns, url)


## Global: postgres threaded connection pool - keeping it simple for demo app
try:
    pool = connect(numc=MAX_DBCON_POOL)
except Exception as e:
    log.error(e)
    sys.exit(1)

## -------------------------------------------------------------------------- ##
def createdb(conn, schema="schema.sql"):
    """
    Execute DROP and CREATE TABLE statements in the specified SQL file.
    """
    with open(schema, 'r') as f:
        sql = f.read()

    try:
        with conn.cursor() as curs:
            curs.execute(sql)
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

## -------------------------------------------------------------------------- ##
@contextmanager
def transaction(name="transaction", **kwargs):
    # Get the session parameters from the kwargs
    options = {
        "isolation_level": kwargs.get("isolation_level", None),
        "readonly": kwargs.get("readonly", None),
        "deferrable": kwargs.get("deferrable", None),
    }

    try:
        conn = pool.getconn()
        conn.set_session(**options)
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("{} error: {}".format(e.name, e.error))
    finally:
        conn.reset()
        pool.putconn(conn)

## -------------------------------------------------------------------------- ##
def transact(func):
    """
    Creates a connection per-transaction, committing when complete or
    rolling back if there is an exception. It also ensures that the conn is
    closed when we're done.
    """
    @wraps(func)
    def inner(*args, **kwargs):
        with transaction(name=func.__name__) as conn:
            func(conn, *args, **kwargs)
    return inner

## -------------------------------------------------------------------------- ##
@transact
def crud(conn, op, delay, wc = MAX_WORDS_PER_ITER):

    """
    Generates 'wc' number of random words from lorem-ipsum and
    performs CRUD operation specified by 'op' for each word with default delay after operation
    """
    words = lorem.get_word(count=wc, sep=',', func=lambda x: x.upper()).split(',')
    with conn.cursor() as curs:
        for w in words:
            if op == dbops['INSERT']:
                sql = 'INSERT INTO pgfailover.benchtab (ts, status) VALUES (CURRENT_TIMESTAMP, \'%s\');'
            elif op == dbops['READ']:
                sql = 'SELECT ts, status FROM pgfailover.benchtab WHERE status like \'%s\''
            curs.execute(sql % w)
            conn.commit()
            rec = '{:s} {:s}'
            log.debug(rec.format(opsdb[op], w))
            if delay > 0:
                time.sleep(delay)

## -------------------------------------------------------------------------- ##
def display(options):
    """
    Displays command line options and arguments passed
    """
    vals = 'Defaults' if len(sys.argv[1:]) == 0 else 'Values'
    char = '-'
    consvals = ''
    consvals += '\n{:20s}+{:s}'.format(char*20, char*18)
    consvals += '\n{:20s}| {:s}'.format('Arguments', vals)
    consvals += '\n{:20s}+{:s}'.format(char*20, char*18)
    for arg in vars(options):
        consvals += '\n{:20s}|'.format(arg) + ' ' + str(getattr(options, arg))
    consvals += '\n{:20s}+{:s}'.format(char*20, char*18)
    print (consvals)
    if options.prompt:
        print('Enter to continue ...')
        sys.stdin.read(1)


## -------------------------------------------------------------------------- ##
def cleanup():
    try:
        if pool:
            pool.closeall()
    except Exception as e:
        fmt = 'Caught exception: code = {c}: {m}'.format(c = type(e).__name__, m = str(e))
        log.exception(fmt)
        sys.exit(1)


## -------------------------------------------------------------------------- ##
def check():
    """
    Check environment to connect to database (PGDSN) and
    whether we can support another connection pool
    """

    if not os.getenv('PGDSN'):
        raise ValueError("no database url specified")
    sql = 'SELECT numbackends FROM pg_stat_database WHERE datname = (SELECT current_database());'
    num = 0
    try:
        conn = pool.getconn()
        with conn.cursor() as curs:
            curs.execute(sql)
            num = curs.fetchone()[0]
        pool.putconn(conn)
        return num
    except:
        log.error('exceeded max allowed connections for current database')
        sys.exit(1)

## -------------------------------------------------------------------------- ##
def run(options):
    """
    Run various operations (commmands) with customizations
    Available commands: { initdb, rwops }
                initdb: initialize bench database with schema
                 rwops: run CRUD operations
    """

    db_conns = check()
    if db_conns > 16:
        sys.exit(0)

    import threading
    import signal

    if not options.quiet:
        display(options)

    operations = [ getattr(options, arg) for arg in vars(options) ]
    if 'initdb' in operations:
        log.info('creating schema from file %s' % options.schema)
        conn = pool.getconn()
        createdb(conn, options.schema)
        pool.putconn(conn)
        log.info('done creating schema')


    if 'rwops' in operations:

        numwords = min(MAX_WORDS_PER_ITER, int(options.opsperiter))
        def handler(signal_received, frame):
            log.warning('SIGINT or CTRL+C detected. PLEASE WAIT...\n')
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTSTP, signal.SIG_IGN)
            sys.exit(0)

        def write():
            crud(dbops['INSERT'], options.delay, numwords)

        def read():
            crud(dbops['READ'], options.delay, numwords)

        ## Read read/write ratio and adjust if necessary
        rop, wop = map(int, options.rwratio.split(':'))
        if ((rop + wop) > MAX_DBCON_POOL):
            rco = int(rop*MAX_DBCON_POOL*1./(rop + wop))
            wco = int(wop*MAX_DBCON_POOL*1./(rop + wop))
            if rco < wco:
                rco = MAX_DBCON_POOL - max(rco, wco)
                wco = MAX_DBCON_POOL - rco
            elif wco < rco:
                wco = MAX_DBCON_POOL - max(rco, wco)
                rco = MAX_DBCON_POOL - wco
            rop = rco
            wop = wco

        ## Catch Ctrl + C in case running '--forever' is required
        signal.signal(signal.SIGINT, handler)

        log.info('read : write = {} : {}     starting first iteration...'.format(rop,wop))
        num_writes = numwords * wop
        num_reads = numwords * rop
        elapsed = max(num_writes, num_reads)
        while True:
            threads = list()

            ## define multiple db threads - consistent with read / write ratio
            [ threads.append( threading.Thread(target=read) ) for i in range(rop) ]
            [ threads.append( threading.Thread(target=write) ) for i in range(wop) ]

            ## start execution and wait (join) for all of them to terminate
            t0 = datetime.now()
            [ t.start() for t in threads ]
            [ t.join() for t in threads ]
            t1 = datetime.now()
            unit = 's'
            el = elapsed
            if options.delay == 0:
                el *= (t1 - t0).microseconds * 1.e-3
                unit = 'ms'
            else:
                el *= options.delay
            if not options.forever:
                cleanup()
                sys.exit(0)

            log.info('{} reads, {} writes in {:.0f} {}. waiting 1s before next iteration...'.format(num_reads,num_writes,el, unit))
            time.sleep(1)


