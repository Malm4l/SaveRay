# Notices and attributions

## Save file parsing

SaveRay reads Football Manager 27 save files through **fmsave**
(https://github.com/rhiever/fmsave), an open source library released under
the MIT License. All parsing credit belongs to that project. SaveRay itself
only stores the exported data in a local SQLite snapshot and presents it.

## Role catalog data

The role names and their in-possession / out-of-possession phases in
`roles_touchline.json` follow the Football Manager 27 user interface. The
grouping of each role's priority and supporting attributes follows the
editorial role guides published by **Touchline FM**
(https://touchlinefm.com/tactics). Those guides are Touchline FM's own
coaching interpretation and are not official Football Manager attribute
highlights.

The catalog ships as a plain data file on purpose. Anyone may replace it
with a different catalog, for example the official in-game attribute
highlights, without changing the scoring engine in `roles_engine.py`.

## Game data

Football Manager is a trademark of Sports Interactive. SaveRay is an
unofficial fan tool, is not affiliated with Sports Interactive or SEGA,
and reads only save files that the user already owns on their own machine.
No game data is distributed with this repository.
