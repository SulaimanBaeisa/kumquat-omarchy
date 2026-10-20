pragma Singleton
import QtQuick

// Records what the plugin would have started.
QtObject {
  property var calls: []

  function execDetached(command) {
    calls = calls.concat([command])
  }
}
