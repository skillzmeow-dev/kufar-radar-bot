import subprocess
import sys

print("Starting Kufar Radar Bot and KSO Schedule Bot simultaneously...")
p_kufar = subprocess.Popen([sys.executable, "bot.py"])
p_kso = subprocess.Popen([sys.executable, "kso_bot/bot.py"])

try:
    p_kufar.wait()
    p_kso.wait()
except KeyboardInterrupt:
    print("Stopping bots...")
    p_kufar.terminate()
    p_kso.terminate()
