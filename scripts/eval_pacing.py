"""Keep development evaluation calls spaced apart without slowing the app."""
import os
from time import sleep


def paced_cases(cases):
    delay = int(os.environ.get("F1_EVAL_PAUSE_SECONDS", "30"))
    if delay < 0:
        raise ValueError("F1_EVAL_PAUSE_SECONDS must be nonnegative")
    for index, case in enumerate(cases):
        if index:
            sleep(delay)
        yield case
