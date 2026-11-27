"""Keep development evaluation calls spaced apart without slowing the app."""
import os
from time import sleep


def paced_cases(cases, default_delay=30):
    delay = int(os.environ.get("F1_EVAL_PAUSE_SECONDS", str(default_delay)))
    if delay < 0:
        raise ValueError("F1_EVAL_PAUSE_SECONDS must be nonnegative")
    for index, case in enumerate(cases):
        if index:
            sleep(delay)
        yield case
