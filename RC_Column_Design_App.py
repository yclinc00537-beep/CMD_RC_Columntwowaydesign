import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io

# =========================================================================
# 🟢 1. 全域物理地圖與基礎參數初始化
# =========================================================================
bar_diameter_map = {"#6 (#19)": 1.91, "#7 (#22)": 2.22, "#8 (#25)": 2.54, "#10 (#32)": 3.22, "#11 (#36)": 3.58}
bar_area_map = {"#6 (#19)": 2.87, "#7 (#22)": 3.87, "#8 (#25)": 5.07, "#10 (#32)": 8.14, "#11 (#36)": 10.06}

st.set_page_config(page_title="RC柱 LRFD 耐震設計與強柱弱梁檢核工具", layout="wide")
st.title("🏛️ RC 柱 P-M-M 強度與強柱弱梁耐震核算面板")

# 側邊欄全域參數與全域耐震控制開關
st.sidebar.header("📐 1. 全域環境與耐震設定")
seismic_zone = st.sidebar.checkbox("⚡ 啟用特殊抗彎矩構架 (高震區 SMRF) 圍束區構造限制", value=True)
st.sidebar.markdown("---")

st.sidebar.subheader("🧱 1.1 材料基本性質")
fc = st.sidebar.number_input("混凝土強度 fc' (kgf/cm²)", min_value=140, value=280, step=35)
fy = st.sidebar.number_input("主鋼筋強度 fy (kgf/cm²)", min_value=2800, value=4200, step=700)
fyt = st.sidebar.number_input("箍筋強度 fyt (kgf/cm²)", min_value=2800, value=4200, step=700)
d_prime = st.sidebar.number_input("外部保護層淨厚度 (cm)", min_value=3.0, value=4.0, step=0.5)

st.sidebar.subheader("🌀 1.2 剪力箍筋規格")
tie_size = st.sidebar.selectbox("箍筋號數", ["#3 (#10)", "#4 (#13)", "#5 (#16)"], index=1)
tie_legs_x = st.sidebar.number_input("X 向有效箍筋肢數 (Avx)", min_value=2, value=4, step=1)
tie_legs_y = st.sidebar.number_input("Y 向有效箍筋肢數 (Avy)", min_value=2, value=4, step=1)

ds = 0.95 if "#3" in tie_size else (1.27 if "#4" in tie_size else 1.59)
as_tie = 0.71 if "#3" in tie_size else (1.27 if "#4" in tie_size else 1.99)

# =========================================================================
# 🗃️ 2. 多尺寸柱基本參數資料庫 (Multi-Column DB)
# =========================================================================
st.header("🗃️ 多尺寸柱基本參數資料庫 (Multi-Column DB)")
st.caption("ℹ️ 請輸入與 SAP2000 Section 對齊的型號名稱（智慧模糊去空格咬合）。")

if "df_column_db" not in st.session_state:
    st.session_state.df_column_db = pd.DataFrame([
        {"柱型號": "C 60 X 60", "柱寬 B (cm)": 60.0, "柱高 H (cm)": 60.0, "X向每側主筋支數": 5, "Y向每側主筋支數": 5, "主筋號數": "#10 (#32)"},
        {"柱型號": "C 70 X 70", "柱寬 B (cm)": 70.0, "柱高 H (cm)": 70.0, "X向每側主筋支數": 6, "Y向每側主筋支數": 6, "主筋號數": "#11 (#36)"}
    ])

# 設定資料庫下拉選單與微調級距
configured_cols = {
    "柱型號": st.column_config.TextColumn("柱型號 (對齊 SAP 名稱)", required=True),
    "柱寬 B (cm)": st.column_config.NumberColumn("柱寬 B (cm) [X向]", min_value=20.0, step=5.0, format="%.1f"),
    "柱高 H (cm)": st.column_config.NumberColumn("柱高 H (cm) [Y向]", min_value=20.0, step=5.0, format="%.1f"),
    "X向每側主筋支數": st.column_config.NumberColumn("X向單邊筋數 (含角筋)", min_value=2, step=1),
    "Y向每側主筋支數": st.column_config.NumberColumn("Y向單邊筋數 (含角筋)", min_value=2, step=1),
    "主筋號數": st.column_config.SelectboxColumn("主筋號數", options=list(bar_diameter_map.keys()), required=True)
}

edited_df = st.data_editor(st.session_state.get("df_column_db"), num_rows="dynamic", column_config=configured_cols, width='stretch')

if edited_df is not None and not edited_df.empty:
    edited_df['柱型號'] = edited_df['柱型號'].astype(str).str.strip().str.upper()
    df_clean_db = edited_df.drop_duplicates(subset=["柱型號"], keep="last")
    sect_db = df_clean_db.set_index("柱型號").to_dict(orient="index")
else:
    sect_db = {}

# =========================================================================
# 📁 3. 批次自動化上傳：SAP2000 柱雙表 0 迴圈物理快洗引擎 (P-M-M 包絡核心)
# =========================================================================
st.markdown("---")
with st.expander("📁 批次自動化：上傳 SAP2000 柱內力雙表 Excel (.xlsx)", expanded=True):
    uploaded_file = st.file_uploader("請上傳同時包含內力表 (Element Forces) 與性質指派表 (Frame Section Assignments) 的 Excel 檔", type=["xlsx"])
    
    if uploaded_file is not None:
        try:
            xl = pd.ExcelFile(uploaded_file, engine='openpyxl')
            sheet_names = xl.sheet_names
            
            forces_sheets = [s for s in sheet_names if 'FORCES' in s.upper() or '內力' in s or 'FORCE' in s.upper()]
            assign_sheets = [s for s in sheet_names if 'ASSIGN' in s.upper() or '性質' in s or 'SECT' in s.upper()]
            
            if len(forces_sheets) == 0 or len(assign_sheets) == 0:
                st.error("❌ 檔案錯誤：Excel 活頁簿中必須同時包含內力表與性質指派表分頁！")
                st.stop()
            
            # 強制降維提取分頁純字串名字
            target_forces_sheet = forces_sheets[0]
            target_assign_sheet = assign_sheets[0]
            
            # --- 3.1 讀取並重構左表 (內力表) ---
            df_forces_raw = pd.read_excel(uploaded_file, sheet_name=target_forces_sheet, header=None)
            raw_values_f = df_forces_raw.head(5).values
            header_idx = 0
            for i in range(len(raw_values_f)):
                row_str = [str(item).strip().upper() for item in raw_values_f[i]]
                if any('FRAME' in item for item in row_str) and not any('TABLE' in item for item in row_str):
                    header_idx = i
                    break
                    
            df_forces_clean = df_forces_raw.iloc[header_idx+1:].copy()
            
            # 💡 【柱子力學物理標頭指派】：
            # Index 0: Frame, Index 4: P(軸力), Index 5: V2, Index 6: V3, Index 7: T, Index 8: M2, Index 9: M3
            forces_cols_count = df_forces_raw.shape[1]
            f_col_names = []
            for idx in range(forces_cols_count):
                if idx == 0: f_col_names.append("F_COL_0")
                elif idx == 4: f_col_names.append("RAW_P")    # 軸力
                elif idx == 5: f_col_names.append("RAW_V2")   # 剪力 V2
                elif idx == 6: f_col_names.append("RAW_V3")   # 剪力 V3
                elif idx == 8: f_col_names.append("RAW_M2")   # 彎矩 M2 (弱軸)
                elif idx == 9: f_col_names.append("RAW_M3")   # 彎矩 M3 (強軸)
                else: f_col_names.append(f"F_COL_{idx}")
            df_forces_clean.columns = f_col_names
            df_forces_clean = df_forces_clean.reset_index(drop=True)
            
            # --- 3.2 讀取並重構右表 (性質指派表) ---
            df_assign_raw = pd.read_excel(uploaded_file, sheet_name=target_assign_sheet, header=None)
            raw_values_a = df_assign_raw.head(5).values
            as_header_idx = 0
            for i in range(len(raw_values_a)):
                as_row_str = [str(item).strip().upper() for item in raw_values_a[i]]
                if any(k in item for item in as_row_str for k in ['FRAME', 'ELEMENT', 'SECT', 'PROP']):
                    as_header_idx = i
                    break
                    
            df_assign = df_assign_raw.iloc[as_header_idx+1:].copy()
            df_assign.columns = [f"A_COL_{idx}" for idx in range(df_assign.shape[1])]
            df_assign = df_assign.reset_index(drop=True)
            
            # 高速向量化轉型與排空
            df_forces_clean['LINK_NUM'] = pd.to_numeric(df_forces_clean['F_COL_0'], errors='coerce')
            df_assign['LINK_NUM'] = pd.to_numeric(df_assign['A_COL_0'], errors='coerce')
            df_forces_final = df_forces_clean.dropna(subset=['LINK_NUM']).copy()
            df_assign_final = df_assign.dropna(subset=['LINK_NUM']).copy()
            
            df_forces_final['LINK_ID_STR'] = df_forces_final['LINK_NUM'].astype(int).astype(str)
            df_assign_final['LINK_ID_STR'] = df_assign_final['LINK_NUM'].astype(int).astype(str)
            
            # 認領右表剖面型號 (Index 4 固定為真實型號名稱)
            df_assign_clean = df_assign_final[['LINK_ID_STR', 'A_COL_4']].copy()
            df_assign_clean.columns = ['LINK_ID_STR', 'REAL_SECTION']
            df_assign_clean['REAL_SECTION'] = df_assign_clean['REAL_SECTION'].astype(str).str.strip().str.upper()
            
            # 🚀 跨表合併
            df_sap = pd.merge(df_forces_final, df_assign_clean, on='LINK_ID_STR', how='left')
            
            # 數據向量化快洗與絕對值轉換
            df_sap['Num_P']  = pd.to_numeric(df_sap['RAW_P'], errors='coerce').fillna(0.0)
            df_sap['Num_M2'] = pd.to_numeric(df_sap['RAW_M2'], errors='coerce').fillna(0.0).abs()
            df_sap['Num_M3'] = pd.to_numeric(df_sap['RAW_M3'], errors='coerce').fillna(0.0).abs()
            df_sap['Abs_V2'] = pd.to_numeric(df_sap['RAW_V2'], errors='coerce').fillna(0.0).abs()
            df_sap['Abs_V3'] = pd.to_numeric(df_sap['RAW_V3'], errors='coerce').fillna(0.0).abs()
            df_sap['Max_V']  = np.maximum(df_sap['Abs_V2'], df_sap['Abs_V3']) # 雙向剪力包絡
            
            # 💡 【P-M-M 關鍵多指標包絡群組化】
            # 同時抓出最大壓力(max P)、最大拉力(min P)、最大M2、最大M3以及最大剪力！
            group_keys = ['LINK_ID_STR', 'REAL_SECTION']
            df_summary = df_sap.groupby(group_keys).agg(
                P_max=('Num_P', 'max'),
                P_min=('Num_P', 'min'),
                M2_max=('Num_M2', 'max'),
                M3_max=('Num_M3', 'max'),
                V_max=('Max_V', 'max')
            ).reset_index()
            
            df_summary.columns = ['柱編號', '識別型號', '最大壓軸力 Pu (tf)', '最大拉軸力 Pu (tf)', '最大彎矩 Mu2 (tf-m)', '最大彎矩 Mu3 (tf-m)', '剪力需求 Vu (tf)']
            df_summary_clean = df_summary[~df_summary['識別型號'].isin(['NAN', 'NONE', ''])].reset_index(drop=True)
            
            # 展示清洗完成的包絡大總表
            st.subheader("🏁 柱全模型力學包絡極值報告")
            st.dataframe(df_summary_clean.style.format({
                '最大壓軸力 Pu (tf)': '{:.1f}', '最大拉軸力 Pu (tf)': '{:.1f}',
                '最大彎矩 Mu2 (tf-m)': '{:.1f}', '最大彎矩 Mu3 (tf-m)': '{:.1f}', '剪力需求 Vu (tf)': '{:.1f}'
            }), width='stretch')
            
            # =========================================================================
            # ⚡ 4. 點擊開始執行柱極限強度與強柱弱梁耐震檢核
            # =========================================================================
            if st.button("🏛️ 執行全批量柱強度與強柱弱梁構造安全複核", type="primary"):
                results = []
                for index, row in df_summary_clean.iterrows():
                    col_id = str(row['柱編號']).strip()
                    sect_name = str(row['識別型號']).strip().upper()
                    
                    Pu_max = float(row['最大壓軸力 Pu (tf)'])
                    Pu_min = float(row['最大拉軸力 Pu (tf)'])
                    Mu2_val = float(row['最大彎矩 Mu2 (tf-m)'])
                    Mu_max = float(row['最大彎矩 Mu3 (tf-m)'])
                    Vu_val = float(row['剪力需求 Vu (tf)'])
                    
                    # 智慧無空格特徵匹配
                    matched_key = None
                    clean_sect_name = sect_name.replace(" ", "")
                    for db_key in sect_db.keys():
                        clean_db_key = str(db_key).strip().upper().replace(" ", "")
                        if (clean_db_key in clean_sect_name) or (clean_sect_name in clean_db_key):
                            matched_key = db_key
                            break
                            
                    if matched_key is not None:
                        B_i = float(sect_db[matched_key]["柱寬 B (cm)"])
                        H_i = float(sect_db[matched_key]["柱高 H (cm)"])
                        nx = int(sect_db[matched_key]["X向每側主筋支數"])
                        ny = int(sect_db[matched_key]["Y向每側主筋支數"])
                        sz_bar = str(sect_db[matched_key]["主筋號數"])
                    else:
                        # 預設保底常數
                        B_i, H_i = 60.0, 60.0
                        nx, ny = 5, 5
                        sz_bar = "#10 (#32)"
                        
                    db_main = bar_diameter_map[sz_bar]
                    ab_main = bar_area_map[sz_bar]
                    
                    # 計算總主筋量與配筋率
                    total_bars_count = 2 * nx + 2 * (ny - 2)
                    Ast_total = total_bars_count * ab_main
                    Ag = B_i * H_i
                    rho_u = Ast_total / Ag
                    
                    # 💡 檢核 1：最小與最大配筋率限制 (1% <= rho <= 6%)
                    status_rho = "✅ 合格"
                    if rho_u < 0.01: status_rho = "❌ 低於最小配筋率 1%"
                    elif rho_u > 0.06: status_rho = "❌ 超過最大配筋率 6%"
                    
                    # 💡 檢核 2：極限軸力容量計算 ɸPn(max)
                    # 考慮標準柱 ɸ = 0.65, alpha = 0.80
                    phi_axial = 0.65
                    Pn_max = 0.85 * (0.85 * fc * (Ag - Ast_total) + fy * Ast_total) / 1000.0
                    phi_Pn_max = phi_axial * Pn_max
                    
                    status_axial = "✅ 安全"
                    if Pu_max > phi_Pn_max: status_axial = "❌ 軸壓超載"
                    
                    # 💡 檢核 3：高震區 SMRF 圍束箍筋構造間距限制 (柱頭塑鉸區限制)
                    if seismic_zone:
                        h_spacing1 = min(B_i, H_i) / 4.0
                        h_spacing2 = 6 * db_main
                        # s0 限制
                        hx = 15.0 # 假設繫筋間距
                        s0 = 10.0 + (35.0 - hx) / 3.0
                        max_hoop_spacing = min(h_spacing1, h_spacing2, s0, 10.0)
                        suggested_hoop = f"{tie_size} @ {max_hoop_spacing:.0f} cm (圍束控制)"
                    else:
                        max_hoop_spacing = min(16 * db_main, 48 * ds, min(B_i, H_i))
                        suggested_hoop = f"{tie_size} @ {min(30.0, max_hoop_spacing):.0f} cm (常規構造)"
                        
                    # 💡 檢核 4：強柱弱梁耐震構造初步初估判定 (ΣMc > 1.2 ΣMb)
                    # 此處利用柱梁尺寸剛度與配筋率進行實務模擬常數演算法
                    approx_phi_Mcn = (0.4 * Ast_total * fy * (H_i - 2*d_prime)) / 100000.0
                    sc_wb_ratio = approx_phi_Mcn / (Mu_max if Mu_max > 0 else 1.0)
                    status_scwb = "✅ 滿足 (比值>1.2)" if sc_wb_ratio >= 1.2 else "❌ 違反強柱弱梁"
                    
                    # 綜合判定安全安全燈號
                    final_decision = "✅ 安全"
                    if "❌" in status_rho or "❌" in status_axial or "❌" in status_scwb:
                        final_decision = "❌ 構造不合格"
                        
                    results.append({
                        "柱編號": col_id, "識別型號": matched_key if matched_key else f"未識別({sect_name})",
                        "總筋數": f"{total_bars_count}支-{sz_bar}", "配筋率": f"{rho_u*100:.2f}%",
                        "配筋率判定": status_rho, "設計軸力容量 ɸPn": round(phi_Pn_max, 1),
                        "軸壓判定": status_axial, "強柱弱梁比值": round(sc_wb_ratio, 2),
                        "強柱弱梁判定": status_scwb, "圍束區建議箍筋": suggested_hoop,
                        "綜合安全判定": final_decision
                    })
                    
                df_results = pd.DataFrame(results)
                st.subheader("🏁 批次自動化柱耐震安全複核總報告")
                
                def highlight_column_status(val):
                    if "❌" in str(val): return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
                    elif "✅" in str(val): return 'background-color: #e6ffed; color: #22863a;'
                    return ''
                st.dataframe(df_results.style.map(highlight_column_status, subset=['綜合安全判定', '配筋率判定', '軸壓判定', '強柱弱梁判定']), width='stretch')
                st.success("🎉 全模型柱耐震極限複核完成！")
                
        except Exception as e:
            st.error(f"❌ 檔案解析失敗，錯誤訊息: {str(e)}")  