# Copyright 2017-2019 Sergej Schumilo, Cornelius Aschermann, Tim Blazytko
# Copyright 2019-2020 Intel Corporation
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Startup routines for kAFL Fuzzer.

Spawn a Manager and one or more Worker processes, where Manager implements the
global fuzzing queue and scheduler and Workers implement mutation stages and
Qemu/KVM execution.

Prepare the kAFL workdir and copy any provided seeds to be picked up by the scheduler.
"""

import multiprocessing
import time
import os
import sys
import logging

from dynaconf import LazySettings

from kafl_fuzzer.common.util import print_banner
from kafl_fuzzer.common.self_check import self_check, post_self_check
from kafl_fuzzer.common.util import prepare_working_dir, copy_seed_files, qemu_sweep, filter_available_cpus
from kafl_fuzzer.common.logger import add_logging_file
from kafl_fuzzer.manager.manager import ManagerTask
from kafl_fuzzer.worker.worker import worker_loader

logger = logging.getLogger(__name__)

def graceful_exit(workers):
    for s in workers:
        s.terminate()

    logger.info("Waiting for Workers to shutdown...")
    time.sleep(1)

    while len(workers) > 0:
        for s in workers:
            if s and s.exitcode is None:
                logger.info("Still waiting on %s (pid=%d)..  [hit Ctrl-c to abort..]" % (s.name, s.pid))
                s.join(timeout=1)
            else:
                workers.remove(s)


def start(settings: LazySettings):

    print_banner("kAFL Fuzzer")

    if not self_check():
        return 1

    workdir   = settings.workdir
    seed_dir   = settings.seed_dir
    num_worker = settings.processes

    if not post_self_check(settings):
        logger.error("Startup checks failed. Exit.")
        return -1

    if not prepare_working_dir(settings):
        logger.error("Failed to prepare working directory. Exit.")
        return -1;

    # initialize logger after workdir purge
    # otherwise the file handler created is removed
    add_logging_file(settings)

    if seed_dir:
        if not copy_seed_files(workdir, seed_dir):
            logger.error("Error when importing seeds. Exit.")
            return 1
    else:
        logger.warn("Warning: Launching without --seed-dir?")
        time.sleep(1)

    # Without -ip0, Qemu will not active PT tracing and we turn into a blind fuzzer
    if not settings.ip0:
        logger.warn("No PT trace region defined.")

    avail, used = filter_available_cpus()
    if num_worker > len(avail):
        logger.error(f"Requested {num_worker} workers but only {len(avail)} vCPUs detected.")
        return 1

    # warn if assigned cpu set seems to be used by other Qemu instances already
    # attempt to confine ourselves to unused set, unless --cpu-offset override was given
    if num_worker + 1 >= len(avail-used):
        logger.warn(f"Warning: Requested {num_worker} workers but {len(used)} out of {len(avail)} vCPUs seem busy?")
        time.sleep(2)
    elif not settings.cpu_offset:
        os.sched_setaffinity(0, avail-used)

    manager = ManagerTask(settings)

    workers = []
    for i in range(num_worker):
        workers.append(multiprocessing.Process(name="Worker " + str(i), target=worker_loader, args=(i,settings)))
        workers[i].start()

    try:
        manager.loop()
    except KeyboardInterrupt:
        logger.info("Received Ctrl-C, killing workers...")
    except SystemExit as e:
        logger.info("Manager exit: " + str(e))
    finally:
        graceful_exit(workers)

    time.sleep(1)
    qemu_sweep("Detected potential qemu zombies, try to kill -9:")
    sys.exit(0)
