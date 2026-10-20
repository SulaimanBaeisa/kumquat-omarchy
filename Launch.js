// Launch logic shared by Overlay.qml and BarWidget.qml.
//
// Everything here is a plain function with no QML dependency, so
// tests/js/launch.test.mjs can run the same file under Node.
//
// Kumquat itself is a separate GTK 4 program (Python). The shell never imports
// it: these helpers only build the argument list for bin/kumquat, which
// Quickshell.execDetached() then starts without going through a shell.

function pluginId() {
  return "io.github.sulaimanbaeisa.kumquat"
}

// Same names as `kumquat --tab`.
function tabs() {
  return ["conversions", "tools", "actions"]
}

// "file:///home/me/x%20y/bin/kumquat" -> "/home/me/x y/bin/kumquat".
// Returns "" for anything that is not a local file URL.
function urlToPath(url) {
  const text = String(url)
  if (text.indexOf("file://") !== 0)
    return ""
  const path = text.substring("file://".length)
  if (path.charAt(0) !== "/")
    return ""
  try {
    return decodeURIComponent(path)
  } catch (error) {
    return ""
  }
}

// Reads the optional JSON payload given to `omarchy-shell shell summon <id> <json>`:
//
//   {"files": ["/abs/path/a.jpg", ...], "tab": "conversions" | "tools" | "actions"}
//
// Never throws. Invalid parts are dropped and described in `problems`, and the
// caller still opens Kumquat (an empty request just opens the file picker).
function parseRequest(payloadJson) {
  const request = { files: [], tab: "", problems: [] }
  if (payloadJson === undefined || payloadJson === null)
    return request
  const text = String(payloadJson).trim()
  if (text === "")
    return request

  let data
  try {
    data = JSON.parse(text)
  } catch (error) {
    request.problems.push("payload is not valid JSON; ignoring it")
    return request
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    request.problems.push("payload must be a JSON object; ignoring it")
    return request
  }

  if (data.tab !== undefined && data.tab !== null && data.tab !== "") {
    if (tabs().indexOf(data.tab) >= 0)
      request.tab = data.tab
    else
      request.problems.push("unknown tab " + JSON.stringify(data.tab) + "; ignoring it")
  }

  if (data.files !== undefined && data.files !== null) {
    if (!Array.isArray(data.files)) {
      request.problems.push("\"files\" must be an array; ignoring it")
    } else {
      for (let i = 0; i < data.files.length; i++) {
        const file = data.files[i]
        // Absolute paths only: they cannot be mistaken for command-line options.
        if (typeof file === "string" && file.charAt(0) === "/" && file.indexOf("\u0000") < 0)
          request.files.push(file)
        else
          request.problems.push("skipped files[" + i + "]: not an absolute path")
      }
    }
  }
  return request
}

// The argv for Quickshell.execDetached(). The launcher runs through /bin/sh so
// it still starts if a copy of the plugin lost its executable bit. `--files`
// goes last because it takes every argument that follows it.
function launchCommand(launcher, request) {
  const command = ["/bin/sh", launcher, "--gui"]
  const wanted = request || { files: [], tab: "" }
  if (wanted.tab)
    command.push("--tab", wanted.tab)
  if (wanted.files && wanted.files.length > 0) {
    command.push("--files")
    for (let i = 0; i < wanted.files.length; i++)
      command.push(wanted.files[i])
  }
  return command
}
