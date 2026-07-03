import json
import pandas as pd
import sys
import os
import requests
import allure

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

@allure.step("同步資料至 Google Sheet")
def sync_to_google_sheet(df, analysis_df, sheet_input, run_name):
    import gspread
    from gspread_dataframe import set_with_dataframe
    from pathlib import Path
    
    current_dir = Path(__file__).parent
    cred_path = current_dir / 'service_account.json'
    if not cred_path.exists():
        cred_path = current_dir.parent / 'service_account.json'
        
    if not cred_path.exists():
        print(f"❌ 找不到憑證檔案 ({cred_path})，無法同步至 Google Sheet。")
        return
        
    try:
        gc = gspread.service_account(filename=str(cred_path))
        print("✅ 成功讀取 Google Sheet 憑證")
    except Exception as e:
        print(f"❌ 讀取 Google Sheet 憑證失敗: {e}")
        return
        
    try:
        if sheet_input.startswith("http"):
            doc = gc.open_by_url(sheet_input)
        elif len(sheet_input) >= 30 and "/" not in sheet_input:  # 雲端 ID 通常很長且不含斜線
            doc = gc.open_by_key(sheet_input)
        else:
            doc = gc.open(sheet_input)  # 若皆非，則視為檔案名稱
    except Exception as e:
        print(f"❌ 開啟 Google Sheet 失敗，請確認名稱、網址或 ID 是否正確且具有編輯權限：{e}")
        return
        
    try:
        data_sheet_title = f"{run_name}_數據" if run_name else "數據"
        try:
            worksheet = doc.worksheet(data_sheet_title)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = doc.add_worksheet(title=data_sheet_title, rows=max(100, len(df)+10), cols=max(20, len(df.columns)+5))
            
        set_with_dataframe(worksheet, df)
        print(f"✅ 成功將 {len(df)} 筆資料同步至 Google Sheet [{data_sheet_title}]")
        
        if analysis_df is not None and not analysis_df.empty:
            analysis_sheet_title = f"{run_name}_追殺局分析" if run_name else "追殺局分析"
            try:
                analysis_ws = doc.worksheet(analysis_sheet_title)
                analysis_ws.clear()
            except gspread.exceptions.WorksheetNotFound:
                analysis_ws = doc.add_worksheet(title=analysis_sheet_title, rows="100", cols="20")
            set_with_dataframe(analysis_ws, analysis_df)
            
            # 加入總結文字
            total_game_rounds = int(analysis_df['總遊玩局數'].sum()) if '總遊玩局數' in analysis_df.columns else 0
            total_kill_rounds = int(analysis_df['追殺局總局數'].sum()) if '追殺局總局數' in analysis_df.columns else 0
            total_wins = int(analysis_df['玩家贏錢局數'].sum()) if '玩家贏錢局數' in analysis_df.columns else 0
            avg_kill_ratio = total_kill_rounds / total_game_rounds if total_game_rounds > 0 else 0
            avg_win_rate = total_wins / total_kill_rounds if total_kill_rounds > 0 else 0
            summary_text = f"所有遊戲總局數: {total_game_rounds}\n風控追殺局總數(殺數): {total_kill_rounds} (佔總局數 {avg_kill_ratio:.2%})\n玩家破殺總局數: {total_wins}\n平均玩家勝率(破殺率): {avg_win_rate:.2%}"
            analysis_ws.update_acell('J2', summary_text)
            
            # 加入百分比堆疊柱狀圖
            row_count = len(analysis_df) + 1
            body = {
                "requests": [{
                    "addChart": {
                        "chart": {
                            "spec": {
                                "title": f"[{run_name}] 各遊戲風控追殺與一般局數佔比" if run_name else "各遊戲風控追殺與一般局數佔比",
                                "basicChart": {
                                    "chartType": "COLUMN",
                                    "legendPosition": "RIGHT_LEGEND",
                                    "stackedType": "PERCENT_STACKED",
                                    "domains": [
                                        {
                                            "domain": {
                                                "sourceRange": {"sources": [{"sheetId": analysis_ws.id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": 1}]}
                                            }
                                        }
                                    ],
                                    "series": [
                                        {
                                            "series": {
                                                "sourceRange": {"sources": [{"sheetId": analysis_ws.id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 4, "endColumnIndex": 5}]}
                                            },
                                            "targetAxis": "LEFT_AXIS",
                                            "color": {"red": 0.86, "green": 0.27, "blue": 0.27} # 追殺局顯示紅色
                                        },
                                        {
                                            "series": {
                                                "sourceRange": {"sources": [{"sheetId": analysis_ws.id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 2, "endColumnIndex": 3}]}
                                            },
                                            "targetAxis": "LEFT_AXIS",
                                            "color": {"red": 0.20, "green": 0.66, "blue": 0.33} # 一般局數顯示綠色
                                        }
                                    ],
                                    "headerCount": 1
                                }
                            },
                            "position": {
                                "overlayPosition": {
                                    "anchorCell": {"sheetId": analysis_ws.id, "rowIndex": 4, "columnIndex": 9},
                                    "widthPixels": 550,
                                    "heightPixels": 380
                                }
                            }
                        }
                    }
                }]
            }
            try:
                doc.batch_update(body)
                print(f"✅ 成功將圓餅圖與結論總結寫入 [{analysis_sheet_title}]")
            except Exception as chart_e:
                print(f"⚠️ 圖表建立失敗 (但不影響純資料同步)：{chart_e}")
            
    except Exception as e:
        print(f"❌ 同步至 Google Sheet 過程發生錯誤：{e}")

@allure.step("獲取資料、進行轉換與風控分析")
def process_data(source_input, output_excel_path, sheet_input="", run_name=""):
    # 支援逗號或空格分隔多個來源
    source_list = [s.strip() for s in source_input.replace(',', ' ').split() if s.strip()]
    all_rows = []

    for source in source_list:
        # 判斷是否為 API 網址
        if source.startswith('http://') or source.startswith('https://'):
            print(f"🔄 正在從 API 獲取資料: {source} ...")
            try:
                # 優化：增加 timeout 保護 (設定 15 秒)，防止 API 伺服器無回應導致腳本永久掛起
                response = requests.get(source, timeout=15)
                response.raise_for_status() # 檢查 HTTP 狀態碼
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"❌ API 請求失敗 ({source})：{e}")
                continue
            except json.JSONDecodeError as e:
                print(f"❌ API 回傳的不是有效的 JSON 格式 ({source})：{e}")
                continue
        else:
            # 否則視為本地檔案處理
            if not os.path.exists(source):
                print(f"錯誤：找不到輸入網址或檔案 {source}")
                continue

            print(f"🔄 正在讀取並解析 JSON 檔案: {source} ...")
            try:
                with open(source, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"❌ JSON 格式錯誤，可能因為資料截斷或大括號未成對 ({source})：{e}")
                continue
            except Exception as e:
                print(f"❌ 無法讀取檔案 ({source})：{e}")
                continue

        # 處理資料格式
        if isinstance(data, dict) and 'rows' in data:
            rows = data['rows']
        elif isinstance(data, list):
            rows = data
        else:
            print(f"❌ 資料格式不符合預期（找不到 'rows' 陣列） ({source})。")
            continue

        if not rows:
            print(f"⚠️ 沒有資料可供轉換 ({source})。")
            continue
            
        all_rows.extend(rows)

    if not all_rows:
        print("⚠️ 所有來源皆沒有資料可供轉換。")
        return [], output_excel_path, None

    print(f"📊 成功讀取 {len(all_rows)} 筆資料，準備轉換為 Excel...")
    df = pd.DataFrame(all_rows)

    # 防呆：確保合併後的資料有內容，避免空資料引發錯誤
    if df.empty:
        print("⚠️ 轉換後的資料表為空，無法產生報表。")
        return [], output_excel_path, None

    # 1. 原始英文欄位對照「博弈產業慣用術語」
    column_mapping = {
        # --- 原有規格 ---
        "walletType": "錢包類型",
        "gameEndTime": "結算時間",
        "account": "玩家帳號(原)",
        "opValue": "操作編號",
        "gameId": "遊戲 ID",
        "gameName": "遊戲名稱",
        "roomName": "房間/廳館",
        "tableId": "桌號",
        "chairId": "座位",
        "category": "遊戲分類",
        "language": "語系",
        "currency": "幣別",
        "gameNo": "局號",
        "banker": "莊閒",
        "roomType": "房間類型/模式",
        "allBet": "投注額",
        "revenue": "派彩",
        "score": "結算後餘額",
        "cellScore": "房間底注",
        "profit": "玩家輸贏",
        
        # --- 新規格欄位 ---
        "gameUserNO": "用戶編號",
        "orderTime": "下單時間",
        "playerAccount": "玩家帳號",
        "type": "交易類型",
        "originScore": "異動前餘額",
        "addScore": "額度異動",
        "newScore": "異動後餘額",
        "ip": "IP",
        "status": "狀態",
        "createUser": "建立者",
        "agentAccount": "代理帳號",
        "orderId": "訂單號",
        "channelId": "渠道 ID",
        "orderType": "訂單類型",
        "orderStatus": "訂單狀態",
        "curScore": "當前分數",
        "orderIP": "訂單 IP",
        "channelName": "渠道名稱",
        "timezone": "時區"
    }

    # 執行欄位名稱替換
    df.rename(columns=column_mapping, inplace=True)

    # 2. 數值欄位型態轉換 (移除逗號並轉為浮點數)，讓 Excel 更好排序與計算
    # 移到前面以便後續計算 RTP 等數值
    numeric_cols = [
        "投注額", "派彩", "結算後餘額", "房間底注", "玩家輸贏",
        "異動前餘額", "額度異動", "異動後餘額", "當前分數"
    ]
    for col in numeric_cols:
        if col in df.columns:
            # 優化：改用 pd.to_numeric(errors='coerce')，遇到 "-" 或空值等非數字字串時會安全轉為 NaN
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce')

    # --- 博弈特化：計算 RTP (返回率) ---
    if "投注額" in df.columns and "派彩" in df.columns:
        df["RTP(數值)"] = df.apply(
            lambda row: row["派彩"] / row["投注額"] if pd.notna(row["投注額"]) and row["投注額"] > 0 else 0,
            axis=1
        )
        df["RTP(%)"] = df["RTP(數值)"].apply(lambda x: f"{x:.2%}")

    # --- 優化 1：資料排序與時間格式化 ---
    if "結算時間" in df.columns:
        # 將字串轉為 datetime 格式，並過濾掉錯誤格式
        df["結算時間"] = pd.to_datetime(df["結算時間"], errors='coerce')
        # 依照結算時間降冪排列 (最新資料排在最上方)
        df.sort_values(by="結算時間", ascending=False, inplace=True)
        # 再轉回易讀的字串格式，捨棄 NaT
        df["結算時間"] = df["結算時間"].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    # --- 優化 2：精簡與重排欄位 (讓報表更符合博弈營運查看習慣) ---
    # 定義最重要、會頻繁查看的優先欄位 (排在表格最左邊)
    preferred_order = [
         "結算時間", "玩家帳號", "代理帳號", "遊戲名稱", "房間/廳館", "房間類型/模式", 
         "局號", "莊閒", "投注額", "派彩", "玩家輸贏", "RTP(%)", "結算後餘額", "交易類型", "額度異動", "狀態", "訂單號"
    ]
    # 定義要從最後報表中徹底隱藏的系統除錯欄位
    drop_columns = ["渠道 ID", "渠道名稱", "時區", "IP", "訂單 IP", "語系", "錢包類型", "建立者", "RTP(數值)"]
    
    # 執行移除
    cols_to_drop = [c for c in drop_columns if c in df.columns]
    if cols_to_drop:
         df.drop(columns=cols_to_drop, inplace=True)

    # 執行重排：優先欄位在前，其餘未列出的剩餘欄位往後放
    existing_preferred = [c for c in preferred_order if c in df.columns]
    other_columns = [c for c in df.columns if c not in preferred_order]
    df = df[existing_preferred + other_columns]

    # --- 新增：風控分析 - 計算各遊戲在追殺模式(防守局)中玩家破殺的機率 ---
    analysis_df = None
    analysis_results = []
    analysis_path = None
    if '房間類型/模式' in df.columns and '玩家輸贏' in df.columns and '遊戲名稱' in df.columns:
        print("\n🔍 正在分析各遊戲的風控與追殺局數據...")
        
        # 確保房間類型為字串，去除首尾空白
        df['房間類型/模式_str'] = df['房間類型/模式'].astype(str).str.strip()
        
        # 定義追殺局的代碼
        kill_modes = ['ptk', 'K', 'T', 'B']

        # 改用 df groupby 遊戲名稱，以取得該遊戲的總局數
        for game_name, group in df.groupby('遊戲名稱'):
            total_game_rounds = len(group)
            
            # 計算房間類型為 N 和 D 以外的局數
            non_nd_rounds = len(group[~group['房間類型/模式_str'].isin(['N', 'D'])])
            
            # 篩選追殺局 (房間類型完全符合上述 4 種代碼之一)
            kill_group = group[group['房間類型/模式_str'].isin(kill_modes)]
            total_kill_rounds = len(kill_group)
            
            # 計算殺局佔總局數量的比例
            kill_ratio = total_kill_rounds / total_game_rounds if total_game_rounds > 0 else 0
            
            # 假設「玩家輸贏 > 0」代表玩家贏錢(破殺)
            win_rounds = len(kill_group[kill_group['玩家輸贏'] > 0])
            win_rate = win_rounds / total_kill_rounds if total_kill_rounds > 0 else 0
            
            print(f"  - [{game_name}] 總局數: {total_game_rounds} | 非N/D局數: {non_nd_rounds} | 追殺局共 {total_kill_rounds} 局 (佔比: {kill_ratio:.2%}) | 玩家破殺 {win_rounds} 局 (破殺率: {win_rate:.2%})")
            
            # 將分析數據加進清單，以便後續匯出
            analysis_results.append({
                "遊戲名稱": game_name,
                "總遊玩局數": total_game_rounds,
                "一般/其他局數": total_game_rounds - total_kill_rounds,
                "非N與D以外局數": non_nd_rounds,
                "追殺局總局數": total_kill_rounds, # 保持原名以相容Google Sheet寫入
                "殺局佔比": f"{kill_ratio:.2%}",
                "玩家贏錢局數": win_rounds,  # 保持原名以相容Google Sheet寫入
                "破殺率(勝率)": f"{win_rate:.2%}",
                "風控警示(>5%)": "🚨 異常(需關注)" if win_rate > 0.05 else "正常"
            })

            # 若贏錢比例超過 5%，輸出特別警示
            if win_rate > 0.05 and total_kill_rounds > 0:
                print(f"🚨【風控警示】{game_name} 在追殺局中，玩家破殺率高達 {win_rate:.2%} (超過 5%)！可能有被針對或數值異常！")

        # 移除暫存欄位
        df.drop(columns=['房間類型/模式_str'], inplace=True)
            
        # --- 將分析過後的結果匯出為另一份 Excel ---
        if analysis_results:
                try:
                    analysis_df = pd.DataFrame(analysis_results)
                    # 決定分析報告的檔名 (例如把原本的 .xlsx 改成 _追殺局分析.xlsx)
                    if '_數據.xlsx' in output_excel_path:
                        analysis_path = output_excel_path.replace('_數據.xlsx', '_追殺局分析.xlsx')
                    elif output_excel_path.endswith('.xlsx'):
                        analysis_path = output_excel_path.replace('.xlsx', '_追殺局分析.xlsx')
                    else:
                        analysis_path = output_excel_path + "_追殺局分析.xlsx"
                        
                    analysis_df.to_excel(analysis_path, index=False, engine='openpyxl')
                    print(f"📊 [分析報告] 追殺局統整結果已成功匯出至：{analysis_path}")
                except PermissionError:
                    print(f"❌ 追殺局統整結果匯出失敗：檔案【{analysis_path}】可能正在被開啟，請先關閉檔案！")
                except Exception as e:
                    print(f"❌ 追殺局統整結果匯出失敗：{e}")
            # -----------------------------------------
        else:
            print("  - ⚠️ 目前資料中未發現「追殺局」。(若追殺局使用代碼表示，請於程式中修改篩選條件)")
    print("\n")
    # ---------------------------------------------

    # 3. 匯出 Excel
    try:
        # --- 優化 3：自動調整 Excel 欄寬並凍結首列，避免打開時文字擠成一團 ---
        with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='資料明細', index=False)
            worksheet = writer.sheets['資料明細']
            
            # 設定凍結第一列
            worksheet.freeze_panes = "A2"
            
            # 動態評估並調整各欄位寬度
            from openpyxl.utils import get_column_letter
            for idx, col in enumerate(df.columns):
                # 評估「欄位名稱」與「內容」的最大長度 (將中文計為較寬的字元寬度)
                try:
                    content_max = int(df[col].map(lambda x: len(str(x))).max()) if not df[col].empty else 0
                except:
                    content_max = 0
                max_len = max(content_max, len(str(col)) * 1.5)
                # 給予些許緩衝並設定寬度上限，避免某些異常長度撐破版面
                adjusted_width = min(max_len + 3, 35)
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = adjusted_width

        print(f"✅ 成功將完整的資料轉換為 Excel 並儲存於：{output_excel_path}")
    except PermissionError:
        print(f"❌ 匯出 Excel 失敗：檔案【{output_excel_path}】可能正在被其他程式 (如 Excel) 開啟，請先關閉該檔案後重試！")
    except Exception as e:
        print(f"❌ 匯出 Excel 失敗：{e}")
        print("💡 提示：請確認是否有安裝必要的套件 (pip install pandas openpyxl)")

    # 4. 同步資料到 Google Sheet
    if sheet_input:
        print(f"\n🔄 準備將資料同步至 Google Sheet...")
        sync_to_google_sheet(df, analysis_df, sheet_input, run_name)
        
    return analysis_results, output_excel_path, analysis_path

if __name__ == '__main__':
    try:
        input_source = ""
        sheet_input = ""
        run_name = ""
        
        # 也可以透過命令列參數修改輸入與輸出檔名
        if len(sys.argv) > 1:
            input_source = " ".join(sys.argv[1:])
            
        # 如果沒透過命令列參數傳入來源，則預設使用寫死的 API 網址
        if not input_source:
            # 這裡寫死兩組 API (自動帶入您原本輸入的遊戲盈虧與玩家金額)
            input_source = "http://192.168.37.6:8087/practice_data?key=winlose http://192.168.37.6:8087/practice_data?key=usermoney"
            print(f"👉 未輸入參數，預設讀取 API: \n   {input_source}")
                
            run_name = input("請輸入本次執行的分析名稱 (例如 api-1，預設將使用當下時間命名分頁): ").strip()
            if not run_name:
                import datetime
                run_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                # 防呆：移除不合法的 Windows 檔名字元，避免存檔錯誤
                import re
                run_name = re.sub(r'[\\/*?:"<>|]', '_', run_name)

            sheet_input = input("\n請輸入目標 Google Sheet 標題名稱、雲端 ID 或網址\n(若不需要同步請直接按 Enter 跳過): ").strip()

        # 決定本地的輸出檔案名稱
        output_file = f"{run_name}_數據.xlsx" if run_name else "game_records.xlsx"
        process_data(input_source, output_file, sheet_input, run_name)
    except KeyboardInterrupt:
        print("\n⚠️ 程式已由使用者強制中斷。")
    except Exception as e:
        print(f"\n❌ 發生未預期的系統錯誤：{e}")
