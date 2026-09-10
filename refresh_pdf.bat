@echo off
cd C:\Users\tony_chen\Documents\projects\crashout
python -m venv .venv
call .venv\Scripts\activate
python -m ao3_bookmarks --formats PDF --limit 10 --v

pause