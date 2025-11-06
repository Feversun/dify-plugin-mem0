import os

# Disable telemetry/analytics to avoid PostHog timeouts in restricted networks
os.environ.setdefault("POSTHOG_DISABLED", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
# Best-effort vendor-specific opt-outs (safe no-ops if unsupported)
os.environ.setdefault("MEM0_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DIFY_PLUGIN_DISABLE_TELEMETRY", "1")

from dify_plugin import DifyPluginEnv, Plugin

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == "__main__":
    plugin.run()
