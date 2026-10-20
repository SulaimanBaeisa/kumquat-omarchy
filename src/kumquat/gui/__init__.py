"""Kumquat's GTK4 front end.

`app.run_gui` starts the application, `wheel.WheelWindow` is its one window,
`picker` is the embedded file browser and `theme`/`css` style it from the
Omarchy palette. Importing this package never imports GTK; the submodules load
`gi` only when a window is actually built.
"""
