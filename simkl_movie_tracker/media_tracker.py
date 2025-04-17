# media_tracker.py

import pygetwindow as gw
from guessit import guessit

def get_active_window_title():
    window = gw.getActiveWindow()
    if window:
        return window.title
    return None

def parse_movie_title(window_title):
    guess = guessit(window_title)
    return guess.get('title')