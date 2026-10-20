# Hyprland integration — floating shelf + terminal binds

Brings the `float` action (keep files in a floating shelf pinned to a
screen edge) and `openTerminal` to Hyprland. The shelf itself is
`~/.cache/kumquat-shelf.json` (written by
`kumquat.actions.float_shelf`, `{"files": [...]}`); Hyprland only
floats/pins its window.

## Shelf: float + pin the active window

```ini
# Float the active window (what float_shelf runs after writing the manifest)
bind = SUPER, F, exec, hyprctl dispatch togglefloating
# Pin it so it follows you across workspaces (floating only)
bind = SUPER_SHIFT, F, exec, hyprctl dispatch pin
```

Manual equivalent:

```sh
hyprctl dispatch togglefloating
hyprctl dispatch pin
```

## Shelf window rule (optional)

Keep shelf windows floating + centred by class/title — append to
`~/.config/hypr/hyprland.conf`:

```ini
windowrulev2 = float, class:^(kumquat-shelf)$
windowrulev2 = center, class:^(kumquat-shelf)$
windowrulev2 = size 40% 60%, class:^(kumquat-shelf)$
```

## Terminal binds (openTerminal)

`kumquat.actions.open_terminal` uses `$TERMINAL`, falling back to
`kitty / foot / alacritty / ghostty / wezterm / gnome-terminal / xterm`
(first present wins). Bind a terminal in the current directory:

```ini
$terminal = kitty  # or foot, ghostty, ... (must match $TERMINAL)
bind = SUPER, Return, exec, $terminal
# Open one in a specific folder:
bind = SUPER_SHIFT, Return, exec, $terminal ~/projects
```

Headless/agent-env note (repo-wide rule): `wl-copy`/`hyprctl` are
absent there, so `copy_paths`/`copy_files`/`float_shelf` raise
`BackendMissing` until run on a real Wayland/Hyprland host.
