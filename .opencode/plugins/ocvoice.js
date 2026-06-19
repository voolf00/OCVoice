/**
 * OCVoice Plugin for OpenCode
 *
 * Auto-starts the OCVoice voice control daemon when the OpenCode server
 * is ready, and stops it when the server shuts down.
 *
 * Requires: ocv (or ocvoice) in PATH
 *
 * Install: copy to .opencode/plugins/ocvoice.js
 */

export const OCVoicePlugin = async ({ project, client, $, directory, worktree }) => {
  let daemonStarted = false

  console.log("[OCVoice] Plugin loaded")

  return {
    "server.connected": async ({ event }) => {
      if (daemonStarted) return
      console.log("[OCVoice] OpenCode server connected — starting voice daemon...")

      try {
        // Check if ocv or ocvoice is available
        const which = await $`which ocv 2>/dev/null || which ocvoice 2>/dev/null`.quiet()
        const launcher = which.stdout.toString().trim() || ""
        const cmd = launcher.includes("ocv") ? "ocv start-voice" : "ocvoice start"

        console.log(`[OCVoice] Launching: ${cmd}`)
        $`${cmd} &`.quiet()

        daemonStarted = true
        console.log("[OCVoice] Voice daemon started")
      } catch (e) {
        console.log(`[OCVoice] Could not start daemon: ${e.message}`)
        console.log("[OCVoice] Install with: cd OCVoice && ./install.sh")
      }
    },

    "command.executed": async ({ event }) => {
      // Handle /voice command — delegate to shell
      if (event.command === "voice") {
        try {
          const status = await $`ocv status`.quiet()
          console.log("[OCVoice] Status:\n" + status.stdout.toString())
        } catch (e) {
          console.log("[OCVoice] ocv not found in PATH")
        }
      }
    },
  }
}
