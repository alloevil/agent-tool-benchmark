#!/usr/bin/env bun
// Thin harness around the vendored Cline replace_in_file applier
// (vendor/cline_diff.ts, constructNewFileContent).
//
// stdin:  JSON {"original": "<current file content>", "diff": "<Cline SEARCH/REPLACE payload>"}
// stdout: JSON {"ok": true, "content": "<new file content>"}
//     or  JSON {"ok": false, "error": "<message>"}  (exit code 1)
//
// The vendored code is used exactly as Cline calls it for a completed
// replace_in_file tool call: constructNewFileContent(diff, original, isFinal=true)
// with the default "v1" strategy.

import { constructNewFileContent } from "./cline_diff"

const input = JSON.parse(await Bun.stdin.text())
try {
	const content = await constructNewFileContent(input.diff, input.original, true)
	console.log(JSON.stringify({ ok: true, content }))
} catch (e) {
	console.log(JSON.stringify({ ok: false, error: String(e) }))
	process.exit(1)
}
