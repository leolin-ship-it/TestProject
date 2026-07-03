import os
import sys
import subprocess
import datetime
import re
import webbrowser
from pathlib import Path
import socket
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

# 強制將標準輸出編碼重設為 UTF-8，防止 Windows 環境下因 Emoji 產生 UnicodeEncodeError 崩潰
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def setup_java_env():
    """自動尋找並設置 Java 環境變數，避免使用者需要重啟終端機"""
    if not os.environ.get("JAVA_HOME") or "java" not in os.environ.get("PATH", "").lower():
        import glob
        # 尋找常見的 JDK 安裝路徑 (Microsoft, Oracle, Eclipse Temurin, Adoptium)
        possible_jdks = (
            glob.glob(r"C:\Program Files\Microsoft\jdk-*") +
            glob.glob(r"C:\Program Files\Java\jdk-*") +
            glob.glob(r"C:\Program Files\Eclipse Foundation\jdk-*") +
            glob.glob(r"C:\Program Files\Eclipse Adoptium\jdk-*")
        )
        if possible_jdks:
            # 排序以優先使用版本號較高的 JDK
            java_home = sorted(possible_jdks, reverse=True)[0]
            os.environ["JAVA_HOME"] = java_home
            os.environ["PATH"] = f"{java_home}\\bin;" + os.environ.get("PATH", "")
            print(f"[i] 自動載入 Java 環境：{java_home}")

def find_free_port():
    """動態尋找系統中可用的空閒 Port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def download_progress(block_num, block_size, total_size):
    """顯示檔案下載進度"""
    read_so_far = block_num * block_size
    if total_size > 0:
        percent = min(100, read_so_far * 100 / total_size)
        sys.stdout.write(f"\r[+] 下載進度: {percent:.1f}% ({read_so_far/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB)")
        sys.stdout.flush()
    else:
        sys.stdout.write(f"\r[+] 下載進度: {read_so_far/(1024*1024):.1f}MB")
        sys.stdout.flush()

def setup_cloudflared():
    """自動尋找並安裝 Cloudflare Tunnel 引擎"""
    base_dir = Path(__file__).parent
    cloudflared_path = base_dir / "cloudflared.exe"
    if not cloudflared_path.exists():
        print("\n[*] 偵測到尚未下載 Cloudflare 外網分享引擎，正在下載中 (約 30MB，僅需下載一次)...")
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        try:
            import ssl
            import urllib.request
            # 繞過 Python 在 Windows 下可能發生的 SSL 憑證驗證問題
            ssl._create_default_https_context = ssl._create_unverified_context
            urllib.request.urlretrieve(url, cloudflared_path, download_progress)
            print("\n[v] 下載完成！")
        except Exception as e:
            print(f"\n[x] 下載外網引擎失敗: {e}")
            return None
    return cloudflared_path

def copy_to_clipboard(text):
    """將網址複製到 Windows 剪貼簿"""
    try:
        subprocess.run("clip", input=text.encode('utf-8'), check=True, shell=True)
        return True
    except Exception:
        try:
            subprocess.run(f"powershell -Command \"Set-Clipboard -Value '{text}'\"", shell=True)
            return True
        except Exception:
            return False

def main():
    setup_java_env()
    print("=======================================")
    print("      Allure 風控與數據分析執行器      ")
    print("=======================================")
    
    # 這裡寫死兩組 API (與 convert_to_excel.py 預設相同)
    default_api = "http://192.168.37.6:8087/practice_data?key=winlose http://192.168.37.6:8087/practice_data?key=usermoney"
    print(f"👉 預設讀取 API: \n   {default_api}")
    
    # 輸入本次執行的分析名稱
    run_name = input("\n請輸入本次執行的分析名稱 (例如 api-1，預設將使用當下時間): ").strip()
    if not run_name:
        run_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        run_name = re.sub(r'[\\/*?:"<>|]', '_', run_name)
        
    # 輸入 Google Sheet 資訊
    sheet_input = input("\n請輸入目標 Google Sheet 標題名稱、雲端 ID 或網址\n(若不需要同步請直接按 Enter 跳過): ").strip()

    # 設定環境變數供 pytest 讀取
    os.environ["ALLURE_API_URL"] = default_api
    os.environ["ALLURE_RUN_NAME"] = run_name
    os.environ["ALLURE_SHEET_INPUT"] = sheet_input
    
    # 設定目錄
    base_dir = Path(__file__).parent
    results_dir = base_dir / "allure-results"
    report_dir = base_dir / "allure-report"
    
    # 執行 pytest
    print("\n🚀 開始執行風控數據分析與產生測試報告...")
    
    # 優先使用專案目錄下的虛擬環境 .venv 中的 Python，避免使用者以系統全域 Python 執行時找不到相依套件
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python.resolve())
    else:
        python_exe = sys.executable
        
    pytest_cmd = [
        python_exe, "-m", "pytest", str((base_dir / "test_risk_control.py").resolve()),
        f"--alluredir={results_dir}",
        "--clean-alluredir", # 每次執行前清空舊報告
        "-s"
    ]
    
    result = subprocess.run(pytest_cmd, cwd=str(base_dir))
    
    print("\n-------------------------------------")
    if result.returncode in (0, 1):
        print("✅ 數據分析與測試執行完成！正在產生 Allure 靜態網頁報告...")
        try:
            # 產生單一靜態網頁檔案 (Single-File)
            subprocess.run(["allure", "generate", str(results_dir), "--clean", "-o", str(report_dir), "--single-file"], shell=True, check=True)
            
            single_html_file = report_dir / "index.html"
            
            print(f"\n🌐 報告已成功打包為單一網頁檔案：")
            print(f"👉 {single_html_file.resolve()}")
            print("\n💡 您可以直接將此 HTML 檔案傳送給任何人，對方不需安裝任何軟體，點開即可觀看！")
            
            # 動態尋找可用 Port並啟動本地伺服器
            port = find_free_port()
            print(f"\n[*] 正在部署本地 Web 伺服器 (Port: {port})...")
            
            class SilentHTTPRequestHandler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=str(report_dir), **kwargs)
                def log_message(self, format, *args):
                    pass  # 靜音，不污染終端機輸出

            class ThreadedTCPServer(TCPServer):
                allow_reuse_address = True

            httpd = ThreadedTCPServer(("", port), SilentHTTPRequestHandler)
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            local_url = f"http://localhost:{port}/"
            print(f"[v] 本地伺服器已啟動，網址：{local_url}")
            
            # 自動在預設瀏覽器開啟本地伺服器連結
            webbrowser.open(local_url)
            
            # 準備外網分享
            cloudflared_path = setup_cloudflared()
            tunnel_process = None
            
            try:
                if cloudflared_path:
                    print("\n=======================================")
                    print("[*] 正在啟動臨時外網分享伺服器 (Cloudflare Tunnel)...")
                    
                    # 啟動 Cloudflare Quick Tunnel 映射動態 Port
                    import time
                    tunnel_process = subprocess.Popen(
                        [str(cloudflared_path), "tunnel", "--url", f"http://localhost:{port}"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    
                    print("[*] 正在向 Cloudflare 申請高速外網網址...")
                    tunnel_url = None
                    start_time = time.time()
                    
                    # 讀取輸出，尋找網址，最長等待 15 秒
                    while True:
                        if time.time() - start_time > 15:
                            break
                        line = tunnel_process.stdout.readline()
                        if not line:
                            break
                        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                        if match:
                            tunnel_url = match.group(0)
                            break
                    
                    if tunnel_url:
                        print(f"\n[v] 申請成功！您的臨時外網分享網址為：")
                        print(f"👉 {tunnel_url}")
                        
                        # 複製到剪貼簿
                        if copy_to_clipboard(tunnel_url):
                            print("📋 網址已自動複製到您的剪貼簿！您可以直接 Ctrl + V 貼給其他人。")
                        else:
                            print("💡 提示：自動複製到剪貼簿失敗，您可以手動複製上述網址。")
                    else:
                        print("\n[x] 申請外網網址超時或失敗。請確認您的網路連線是否正常。")
                else:
                    print("\n[x] 無法載入 Cloudflare 外網分享引擎，跳過外網分享步驟。")
                
                print("\n=======================================")
                print("[!] 注意：本地伺服器運作中，請保持此視窗開啟。")
                print("[!] 若要結束並關閉伺服器，請按下 Ctrl + C 關閉程式。\n")
                
                # 進入等待，直到使用者按 Ctrl+C
                import time
                while True:
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                print("\n[i] 偵測到使用者中斷執行。")
            finally:
                print("\n[*] 正在關閉伺服器與外網連線...")
                if tunnel_process:
                    try:
                        tunnel_process.terminate()
                        tunnel_process.wait(timeout=3)
                    except Exception:
                        pass
                try:
                    httpd.server_close()
                except Exception:
                    pass
                print("[v] 關閉完成。")
                
        except FileNotFoundError:
            print("\n❌ 錯誤：找不到 allure 命令！")
            print("💡 請確認您的終端機已經重新啟動 (以套用新安裝的 Java/Allure 路徑)。")
        except subprocess.CalledProcessError:
            print("\n❌ 產生 Allure 報告時發生錯誤，請確認 Java 是否安裝並已加入 PATH。")
    else:
        print(f"❌ pytest 執行發生錯誤，退出碼: {result.returncode}")
        
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 已取消執行。")
