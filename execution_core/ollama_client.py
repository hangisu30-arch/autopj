import subprocess


def call_ollama(prompt: str, config: dict) -> str:
    model = config["ai"]["executor"]["model"]
    timeout = config["ai"]["executor"].get("timeout", 1800)

    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode("utf-8"),   # 🔥 반드시 bytes로
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            print("Ollama error:",
                  result.stderr.decode("utf-8", errors="ignore"))
            return ""

        return result.stdout.decode("utf-8", errors="ignore").strip()

    except Exception as e:
        print("Ollama exception:", e)
        return ""