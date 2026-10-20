// Runs the plugin's real Launch.js (the file QML imports) under Node.
// Usage: node --test tests/js/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { fileURLToPath } from "node:url"
import vm from "node:vm"

const source = readFileSync(
  fileURLToPath(new URL("../../Launch.js", import.meta.url)),
  "utf8",
)
// Top-level function declarations become properties of the context, which is
// how QML sees them too.
const Launch = vm.createContext({})
vm.runInContext(source, Launch)

const call = (name, ...args) => vm.runInContext(`${name}`, Launch)(...args)
const parse = (payload) => JSON.parse(JSON.stringify(call("parseRequest", payload)))

test("plugin id matches manifest.json", () => {
  const manifest = JSON.parse(
    readFileSync(fileURLToPath(new URL("../../manifest.json", import.meta.url)), "utf8"),
  )
  assert.equal(call("pluginId"), manifest.id)
})

test("tabs are exactly the ones `kumquat --tab` accepts", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(call("tabs"))), ["conversions", "tools", "actions"])
})

test("urlToPath decodes local file URLs", () => {
  assert.equal(call("urlToPath", "file:///home/me/bin/kumquat"), "/home/me/bin/kumquat")
  assert.equal(call("urlToPath", "file:///home/me/my%20plugin/bin/kumquat"), "/home/me/my plugin/bin/kumquat")
  assert.equal(call("urlToPath", "file:///caf%C3%A9/bin/kumquat"), "/café/bin/kumquat")
})

test("urlToPath rejects anything that is not an absolute local file URL", () => {
  for (const bad of ["", "https://example.com/x", "qrc:/x", "file://host/x", "bin/kumquat", "file:///bad%zz", undefined, null]) {
    assert.equal(call("urlToPath", bad), "", `expected empty for ${bad}`)
  }
})

test("an empty or missing payload opens the picker", () => {
  for (const payload of [undefined, null, "", "   ", "{}"]) {
    const request = parse(payload)
    assert.deepEqual(request, { files: [], tab: "", problems: [] }, `payload ${JSON.stringify(payload)}`)
  }
})

test("a full payload is accepted", () => {
  const request = parse(JSON.stringify({ files: ["/a/b.jpg", "/c d/e.pdf"], tab: "actions" }))
  assert.deepEqual(request, { files: ["/a/b.jpg", "/c d/e.pdf"], tab: "actions", problems: [] })
})

test("every documented tab is accepted", () => {
  for (const tab of ["conversions", "tools", "actions"]) {
    assert.equal(parse(JSON.stringify({ tab })).tab, tab)
  }
})

test("bad JSON never throws and is reported", () => {
  for (const payload of ["{", "not json", "[1,2]", "42", "null", '"text"']) {
    const request = parse(payload)
    assert.deepEqual(request.files, [])
    assert.equal(request.tab, "")
    assert.equal(request.problems.length, 1, `payload ${payload}`)
  }
})

test("unknown tabs and non-array files are dropped with a message", () => {
  const request = parse(JSON.stringify({ tab: "evil", files: "/etc/passwd" }))
  assert.equal(request.tab, "")
  assert.deepEqual(request.files, [])
  assert.equal(request.problems.length, 2)
})

test("only absolute string paths survive, so nothing can look like an option", () => {
  const request = parse(
    JSON.stringify({ files: ["/ok.jpg", "--gui", "-x", "relative/a.jpg", "", 7, null, { a: 1 }, "/nul\u0000byte"] }),
  )
  assert.deepEqual(request.files, ["/ok.jpg"])
  assert.equal(request.problems.length, 8)
})

test("launchCommand builds an argv, with --files last", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(call("launchCommand", "/p/bin/kumquat", null))), ["/bin/sh", "/p/bin/kumquat", "--gui"])
  assert.deepEqual(JSON.parse(JSON.stringify(call("launchCommand", "/p/bin/kumquat", { files: [], tab: "" }))), ["/bin/sh", "/p/bin/kumquat", "--gui"])
  const request = { files: ["/a b.jpg", "/c.png"], tab: "tools" }
  assert.deepEqual(JSON.parse(JSON.stringify(call("launchCommand", "/p/bin/kumquat", request))), [
    "/bin/sh", "/p/bin/kumquat", "--gui", "--tab", "tools", "--files", "/a b.jpg", "/c.png",
  ])
})

test("file names stay single argv entries (no shell involved)", () => {
  const nasty = "/tmp/$(touch pwned); `id` 'quote' \"dq\" *.jpg"
  const argv = JSON.parse(JSON.stringify(call("launchCommand", "/p/bin/kumquat", parse(JSON.stringify({ files: [nasty] })))))
  assert.equal(argv.at(-1), nasty)
  assert.equal(argv.length, 5)
})
