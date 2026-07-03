import pytest
import allure
import os
from convert_to_excel import process_data

# 全域變數用於緩存 API 獲取的結果，避免多次發送請求
GLOBAL_DATA = None

def get_analysis_data():
    global GLOBAL_DATA
    if GLOBAL_DATA is None:
        source_input = os.environ.get("ALLURE_API_URL", "http://192.168.37.6:8087/practice_data?key=winlose http://192.168.37.6:8087/practice_data?key=usermoney")
        run_name = os.environ.get("ALLURE_RUN_NAME", "allure_run")
        sheet_input = os.environ.get("ALLURE_SHEET_INPUT", "")
        output_file = f"{run_name}_數據.xlsx" if run_name else "game_records.xlsx"
        
        # 這裡是在 pytest collection 階段呼叫 process_data
        # 由於 pytest collection 不會記錄 allure 步驟，所以 @allure.step 將不會顯示在報告的 setup 中
        # 但我們會在測試案例中附上 Excel 報表
        results, excel_path, analysis_path = process_data(source_input, output_file, sheet_input, run_name)
        GLOBAL_DATA = {
            "results": results,
            "excel_path": excel_path,
            "analysis_path": analysis_path
        }
    return GLOBAL_DATA

def pytest_generate_tests(metafunc):
    """動態生成測試案例，根據 API 回傳的各遊戲分析結果"""
    if "game_info" in metafunc.fixturenames:
        data = get_analysis_data()
        results = data["results"]
        if results:
            # 依據遊戲名稱為每個測試案例命名
            metafunc.parametrize("game_info", results, ids=[r['遊戲名稱'] for r in results])
        else:
            # 如果沒有資料，產生一個 Dummy 案例並標記為 Skip
            metafunc.parametrize("game_info", [{"遊戲名稱": "無追殺局資料", "無資料": True}], ids=["No_Kill_Rounds"])

@allure.feature("風控分析檢測")
@allure.story("各遊戲追殺局玩家破殺率檢測")
def test_game_risk_control(game_info):
    """驗證各遊戲的追殺局(防守局)玩家破殺率是否異常 (> 5%)"""
    data = get_analysis_data()
    
    # 每個測試案例都附加報表 (Allure 允許這樣做，您可以隨時點開)
    if data["excel_path"] and os.path.exists(data["excel_path"]):
        allure.attach.file(data["excel_path"], name="詳細數據報表 (Excel)", attachment_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", extension="xlsx")
    if data["analysis_path"] and os.path.exists(data["analysis_path"]):
        allure.attach.file(data["analysis_path"], name="追殺局分析報表 (Excel)", attachment_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", extension="xlsx")

    if "無資料" in game_info:
        pytest.skip("本次執行未包含任何追殺局資料可供分析。")

    game_name = game_info['遊戲名稱']
    win_rate_str = game_info['破殺率(勝率)']
    kill_rounds = game_info['追殺局總局數']
    
    # 將字串 "18.58%" 轉為 float
    win_rate = float(win_rate_str.strip('%')) / 100

    allure.dynamic.title(f"檢測遊戲: {game_name}")
    allure.attach(str(game_info), name=f"{game_name} 詳細分析數據", attachment_type=allure.attachment_type.TEXT)

    with allure.step(f"驗證破殺率是否低於 5% (當前破殺率: {win_rate_str}, 追殺局共 {kill_rounds} 局)"):
        if kill_rounds > 0:
            assert win_rate <= 0.05, f"風控異常！【{game_name}】的追殺局玩家破殺率高達 {win_rate_str}，超過 5% 門檻，可能有被針對或數值異常！"
        else:
            allure.attach("此遊戲目前無任何追殺局資料", name="備註")
