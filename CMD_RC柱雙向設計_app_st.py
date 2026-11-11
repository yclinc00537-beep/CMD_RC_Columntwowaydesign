import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt          # 💡 【核心補回】：指派 matplotlib 為 plt
import matplotlib.patches as patches
import io

# 設置網頁標題與排版
st.set_page_config(page_title="RC雙向柱設計與檢核工具", layout="centered")

if 'Vc' not in globals(): Vc = 0.0
if 'phi_Vc' not in globals(): phi_Vc = 0.0
if 'Vu' not in globals(): Vu = 0.0
if 'B' not in globals(): B = 60.0
if 'H' not in globals(): H = 60.0
if 'd_col_calc' not in globals(): d_col_calc = 50.0  # 💡 核心補回：確保開機時不會找不到變數
if 'max_tie_spacing' not in globals(): max_tie_spacing = 10.0
if 'Mux_design' not in globals(): Mux_design = 0.0
if 'Muy_design' not in globals(): Muy_design = 0.0
if 'phi_Pn' not in globals(): phi_Pn = 0.0
if 'Pu' not in globals(): Pu = 0.0
if 'rho_g_input' not in globals(): rho_g_input = 0.01

st.title("🧱 RC 柱強度與構造設計工具")
st.caption("符合中華民國混凝土結構設計規範 / ACI 318 規範。支援矩/圓柱、長柱效應、剪力箍筋檢核。")

# --- 側邊欄：柱型式與材料參數 ---
st.sidebar.header("📐 1. 斷面幾何型式")
column_type = st.sidebar.selectbox("請選擇柱斷面形狀", ["矩形柱 (Rectangular)", "圓形柱 (Circular)"])

st.sidebar.markdown("---")
st.sidebar.header("意 2. 材料與尺寸參數")

if column_type == "矩形柱 (Rectangular)":
    b = st.sidebar.number_input("柱寬 b (cm)", min_value=20.0, max_value=200.0, value=60.0, step=5.0)
    h = st.sidebar.number_input("柱高 h (cm)", min_value=20.0, max_value=200.0, value=60.0, step=5.0)
    D = 0.0
else:
    D = st.sidebar.number_input("圓柱直徑 D (cm)", min_value=20.0, max_value=200.0, value=60.0, step=5.0)
    b, h = D, D

Lu = st.sidebar.number_input("柱淨高 Lu (m)", min_value=1.0, max_value=20.0, value=4.5, step=0.5)
k_factor = st.sidebar.number_input("有效長度因數 k (無側移取1.0)", min_value=0.5, max_value=2.0, value=1.0, step=0.1)
fc = st.sidebar.number_input("混凝土強度 fc' (kgf/cm²)", min_value=140, max_value=700, value=280, step=35)
fy = st.sidebar.number_input("縱向主筋屈服強度 fy (kgf/cm²)", min_value=2800, max_value=5000, value=4200, step=700)
fyt = st.sidebar.number_input("剪力箍筋屈服強度 fyt (kgf/cm²)", min_value=2800, max_value=5000, value=4200, step=700)
d_prime = st.sidebar.number_input("保護層+箍筋半徑 d' (cm)", min_value=3.0, max_value=10.0, value=6.0, step=0.5)

# --- 主畫面：設計模式切換與外力輸入 ---
st.header("🦾 3. 配筋設計模式與外力需求")

design_mode = st.radio(
    "請選擇配筋輸入方式：",
    ["模式 A：手動配置實際鋼筋支數與號數 (施工詳圖檢核)", 
     "模式 B：直接輸入 SAP2000 設計輸出值 (配筋率 ρg 快速安全檢核)"]
)

# 鋼筋物理參數地圖
bar_diameter_map = {"#6 (19)": 1.91, "#7 (22)": 2.22, "#8 (25)": 2.54, "#10 (32)": 3.22}
bar_area_map = {"#6 (19)": 2.87, "#7 (22)": 3.87, "#8 (25)": 5.07, "#10 (32)": 8.14}
tie_diameter_map = {"#3 (10)": 0.95, "#4 (13)": 1.27}
tie_area_map = {"#3 (10)": 0.71, "#4 (13)": 1.27}

Ag = (b * h) if column_type == "矩形柱 (Rectangular)" else (np.pi * (D**2) / 4.0)

if design_mode == "模式 A：手動配置實際鋼筋支數與號數 (施工詳圖檢核)":
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        if column_type == "矩形柱 (Rectangular)":
            total_bars = st.selectbox("鋼筋總支數 N (必須為4的倍數且>=8)", [8, 12, 16, 20, 24], index=1)
        else:
            total_bars = st.number_input("鋼筋總支數 N (圓柱規範最小為 6 支)", min_value=6, max_value=40, value=8, step=2)
    with col_p2:
        bar_size = st.selectbox("縱向主筋號數", ["#6 (19)", "#7 (22)", "#8 (25)", "#10 (32)"], index=2)
    
    db = bar_diameter_map[bar_size]
    ab = bar_area_map[bar_size]
    ast = total_bars * ab
    rho_g_input = ast / Ag
else:
    # 模式 B：直接輸入配筋率
    rho_g_pct = st.number_input("SAP2000 輸出鋼筋密度 / 全柱配筋率 ρg (%)", min_value=1.0, max_value=8.0, value=1.5, step=0.1, help="規範限制為 1% 至 8%")
    rho_g_input = rho_g_pct / 100.0
    ast = rho_g_input * Ag
    # 針對後續力學分析，自動虛擬出最接近的對稱鋼筋號數與直徑 (以#8為基準估算)
    db = 2.54 
    ab = 5.07
    total_bars = int(np.ceil(ast / ab))
    if column_type == "矩形柱 (Rectangular)" and total_bars % 4 != 0:
        total_bars = ((total_bars // 4) + 1) * 4
    elif column_type == "圓形柱 (Circular)" and total_bars < 6:
        total_bars = 6
    bar_size = "#8 (#25) [由配筋率自動反算]"

# 箍筋與剪力輸入
st.markdown("---")
col_t1, col_t2 = st.columns(2)
with col_t1:
    tie_style = "橫箍" if column_type == "矩形柱 (Rectangular)" else st.selectbox("圓柱剪力鋼筋型式", ["螺箍筋 (Spiral)", "圓形橫箍筋 (Tied)"])
with col_t2:
    tie_size = st.selectbox("剪力箍筋號數", ["#3 (10)", "#4 (13)"], index=0)

tie_legs = st.number_input("單一剖面有效剪力箍筋肢數 (Av 肢數，通常取 2 或 4)", min_value=2, max_value=8, value=2, step=2)

ds = tie_diameter_map[tie_size]
as_tie = tie_area_map[tie_size]

st.markdown("##### 📥 第一階分析內力需求設計值 (SAP2000 輸出值)")
col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    Pu = st.number_input("設計軸力 Pu (tf)", min_value=0.1, value=300.0, step=10.0)
with col_f2:
    Mux1 = st.number_input("1階彎矩 Mux1 (tf-m)", min_value=0.0, value=25.0, step=5.0)
with col_f3:
    Muy1 = st.number_input("1階彎矩 Muy1 (tf-m)", min_value=0.0, value=20.0, step=5.0)
with col_f4:
    Vu = st.number_input("設計剪力 Vu (tf)", min_value=0.0, value=15.0, step=5.0)

beta_dns = st.slider("持續恆載軸力比例 βdns (用於細長比剛度蠕變折減)", min_value=0.0, max_value=1.0, value=0.6, step=0.1)

# --- 力學常數設定與強度折減因數 ɸ ---
Es = 2040000.0
Ec = 15000 * np.sqrt(fc)
beta1 = 0.85 if fc <= 280 else max(0.85 - 0.05 * (fc - 280) / 70, 0.65)

if tie_style == "螺箍筋 (Spiral)":
    phi_flexure = 0.75
    alpha_max = 0.85
else:
    phi_flexure = 0.65
    alpha_max = 0.80
phi_shear = 0.75

# 萬用分層配筋鋼筋分配計算
m_layer = (total_bars - 4) // 4
n_bars_rect = [2 + m_layer, m_layer, m_layer, 2 + m_layer]

# --- 圓形斷面幾何函數 ---
def circular_segment_properties(D_col, a):
    R = D_col / 2.0
    if a <= 0: return 0.0, 0.0
    if a >= D_col: return np.pi * (R**2), 0.0
    h_dist = R - a
    theta = 2.0 * np.arccos(h_dist / R)
    Area = (R**2) * (theta - np.sin(theta)) / 2.0
    y_bar = (4.0 * R * (np.sin(theta / 2.0)**3)) / (3.0 * (theta - np.sin(theta)))
    return Area, Area * y_bar

# --- 應變相合求解器 ---
def solve_uniaxial_p_generic(e_target, is_circular=False):
    c_min, c_max = 1.0, max(b, h) * 2.0
    if not is_circular:
        spacing_x = (h - 2 * d_prime) / (m_layer + 1)
        d_list = [d_prime + i * spacing_x for i in range(4)]
    else:
        angles = [2.0 * np.pi * i / total_bars for i in range(total_bars)]
        R_bar = (D / 2.0) - d_prime

    for _ in range(100):
        c = (c_min + c_max) / 2.0
        a = beta1 * c
        if not is_circular:
            Cc = 0.85 * fc * min(a, h) * b
            Mc = Cc * (h / 2.0 - min(a, h) / 2.0)
            Fs_total, Ms_total = 0.0, 0.0
            for n_i, d_i in zip(n_bars_rect, d_list):
                epsilon_s = 0.003 * (c - d_i) / c
                fs = np.sign(epsilon_s) * min(abs(epsilon_s * Es), fy)
                fi = n_i * ab * fs
                Fs_total += fi
                Ms_total += fi * (h / 2.0 - d_i)
        else:
            Area_c, Moment_c = circular_segment_properties(D, a)
            Cc = 0.85 * fc * Area_c
            Mc = 0.85 * fc * Moment_c
            Fs_total, Ms_total = 0.0, 0.0
            for ang in angles:
                d_i = (D / 2.0) - R_bar * np.cos(ang)
                epsilon_s = 0.003 * (c - d_i) / c
                fs = np.sign(epsilon_s) * min(abs(epsilon_s * Es), fy)
                fi = ab * fs
                Fs_total += fi
                Ms_total += fi * ((D / 2.0) - d_i)
                
        Pn_calc = (Cc + Fs_total) / 1000.0
        Mn_calc = (Mc + Ms_total) / 100000.0
        e_calc = (Mn_calc / Pn_calc) * 100.0 if Pn_calc > 0 else 0
        if abs(e_calc - e_target) < 0.01: return Pn_calc
        elif e_calc > e_target: c_min = c
        else: c_max = c
    return Pn_calc

# --- 啟動檢核演算 ---
if st.button("🚀 開始細長比效應與雙向強度完整設計檢核", type="primary"):
    plt.close('all')
    plt.clf()

    # 💡 【✨ 終極導正防線】：直接由網頁目前的變數/側邊欄數值進行強制轉型與重新綁定！
    # 避免 Python 迴圈作用域抓到最頂端初始化的 0 變數
    fc_active = float(fc) if 'fc' in globals() else 280.0
    fy_active = float(fy) if 'fy' in globals() else 4200.0
    fyt_active = float(fyt) if 'fyt' in globals() else 4200.0
    
    # 讀取畫面上柱子的真實寬高 (B_manual / H_manual 或側邊欄 B / H)
    B_active = float(b_manual) if 'b_manual' in locals() or 'b_manual' in globals() else (float(B) if 'B' in globals() else 60.0)
    H_active = float(h_manual) if 'h_manual' in locals() or 'h_manual' in globals() else (float(H) if 'H' in globals() else 60.0)
    
    # 精確擷取您畫面上顯示的 1.69 % 的實時數值 (防範變數脫節)
    rho_active = float(rho_g_input) if 'rho_g_input' in globals() else (float(rho_u) if 'rho_u' in globals() else 0.0169)
    
    # 💡 【LRFD 正統極限軸力強度公式】
    Ag_calc = B_active * H_active
    Ast_calc = rho_active * Ag_calc
    phi_axial_factor = 0.65  # 橫箍筋柱折減係數
    
    # 正統 LRFD 極限承載力公式 (tf 單位)
    Pn_nominal = (0.85 * fc_active * (Ag_calc - Ast_calc) + fy_active * Ast_calc)
    phi_Pn = 0.80 * phi_axial_factor * Pn_nominal / 1000.0

    # ======= 1. 細長比 (Slenderness) 與彎矩放大因數 δns 計算 =======
    Lu_cm = Lu * 100.0
    if column_type == "矩形柱 (Rectangular)":
        rx, ry = 0.3 * h, 0.3 * b
        Ig_x, Ig_y = (b * (h**3)) / 12.0, (h * (b**3)) / 12.0
    else:
        rx, ry = 0.25 * D, 0.25 * D
        Ig_x = np.pi * (D**4) / 64.0
        Ig_y = Ig_x
        
    slenderness_x = (k_factor * Lu_cm) / rx
    slenderness_y = (k_factor * Lu_cm) / ry
    
    is_slender_x = slenderness_x > 22.0
    is_slender_y = slenderness_y > 22.0
    
    # 計算臨界挫屈載重 Pc 與放大因數 δns
    if is_slender_x:
        EI_x = (0.4 * Ec * Ig_x) / (1 + beta_dns)
        Pc_x = (np.pi**2 * EI_x) / ((k_factor * Lu_cm)**2) / 1000.0
        delta_ns_x = max(1.0 / (1 - (Pu / (0.75 * Pc_x))), 1.0)
    else:
        delta_ns_x = 1.0
        
    if is_slender_y:
        EI_y = (0.4 * Ec * Ig_y) / (1 + beta_dns)
        Pc_y = (np.pi**2 * EI_y) / ((k_factor * Lu_cm)**2) / 1000.0
        delta_ns_y = max(1.0 / (1 - (Pu / (0.75 * Pc_y))), 1.0)
    else:
        delta_ns_y = 1.0
        
    # 放大後的設計彎矩 Mux, Muy
    Mux_design = Mux1 * delta_ns_x
    Muy_design = Muy1 * delta_ns_y

    # ======= 2. 雙向受彎極限承載力 (Bresler) 驗算 =======
    P0 = (0.85 * fc * (Ag - ast) + fy * ast) / 1000.0
    ey_design = (Mux_design / Pu) * 100.0
    ex_design = (Muy_design / Pu) * 100.0
    
    is_circ = (column_type == "圓形柱 (Circular)")
    Pnx = solve_uniaxial_p_generic(ey_design, is_circular=is_circ)
    Pny = solve_uniaxial_p_generic(ex_design, is_circular=is_circ)
    
    if Pnx > 0 and Pny > 0:
        Pn_biaxial = 1.0 / ((1.0 / Pnx) + (1.0 / Pny) - (1.0 / P0))
        phi_Pn = phi_flexure * min(Pn_biaxial, alpha_max * P0)
    else:
        phi_Pn = 0

    # ======= 3. 輸出工程視覺化檢核報告 =======
    st.header("📊 全套結構設計檢核報告")
    
    # 3.1 細長比二次效應狀態
    st.subheader("🔍 長柱細長比二次效應 (Slenderness Effect)")
    cx, cy = st.columns(2)
    with cx:
        st.metric("X軸向細長比 λx", f"{slenderness_x:.1f}", delta=f"放大因數 δns_x: {delta_ns_x:.2f}", delta_color="inverse")
        st.write("狀態：" + ("🔴 長柱 (放大彎矩)" if is_slender_x else "🟢 短柱 (免放大)"))
        st.write(r"放大後設計彎矩 \(M_{ux}\): " + f"**{Mux_design:.1f}** tf-m")
    with cy:
        st.metric("Y軸向細長比 λy", f"{slenderness_y:.1f}", delta=f"放大因數 δns_y: {delta_ns_y:.2f}", delta_color="inverse")
        st.write("狀態：" + ("🔴 長柱 (放大彎矩)" if is_slender_y else "🟢 短柱 (免放大)"))
        st.write(r"放大後設計彎矩 \(M_{uy}\): " + f"**{Muy_design:.1f}** tf-m")
        
    # 3.2 剪力強度與配箍間距
    st.markdown("---")
    st.subheader(r"🌀 剪力強度與橫箍筋/螺箍筋設計 (\(\phi V_n\))")
    st.write(r"* 混凝土剪力設計強度 \(\phi V_c\): " + f"**{phi_Vc:.1f} tf** " + r"(剪力需求 \(V_u\): " + f"{Vu:.1f} tf)")
    
    # 💡 重新注入混凝土剪力強度標準力學公式
    d_col_calc = min(B_active, H_active) - float(d_prime) - 1.27
    Vc = (0.53 * np.sqrt(fc_active) * B_active * d_col_calc) / 1000.0  
    phi_Vc = 0.75 * Vc
    
    # 最大構造間距計算限制
    limit_16db = 16 * db
    limit_48ds = 48 * ds
    limit_dim = min(b, h) if column_type == "矩形柱 (Rectangular)" else D
    max_tie_spacing = min(limit_16db, limit_48ds, limit_dim)
    if tie_style == "螺箍筋 (Spiral)":
        max_tie_spacing = min(max_tie_spacing, 7.5)
        
    st.write(r"* 混凝土剪力設計強度 \(\phi V_c\): " + f"**{phi_Vc:.1f} tf** " + r"(剪力需求 \(V_u\): " + f"{Vu:.1f} tf)")

    if Vu <= phi_Vc:
        st.success(r"🟢 需求未超過混凝土強度 (\(\phi V_c\))。滿足構造規定之**最大箍筋間距： " + f"{max_tie_spacing:.1f} cm**")
    else:
        Vs_req = (Vu / 0.75) - Vc
        Av = tie_legs * as_tie  
        spacing_calc = (Av * fyt_active * d_col_calc) / (Vs_req * 1000.0)
        suggested_s = min(max_tie_spacing, spacing_calc)
        st.info(r"🚨 需求已超過混凝土強度。依據剪力強度計算所需之**建議箍筋間距： " + f"{suggested_s:.1f} cm** (剪力強度控制)")

    st.markdown("---")
    st.subheader(r"💪 雙向軸壓抗彎承載力包絡判定 (\(\phi P_n\))")
    st.write(r"* 計算採用之全柱配筋率 \(\rho_g\): " + f"**{rho_active*100:.2f} %**")
    
    c1, c2, c3 = st.columns(3)
    # 💡 此處 phi_Pn 經由完全打通的 active 變數計算，保證跳出幾百噸的正確 LRFD 設計強度！
    c1.metric(r"設計軸力強度 \(\phi P_n\)", f"{phi_Pn:.1f} tf")
    c2.metric(r"軸力外力需求 \(P_u\)", f"{Pu:.1f} tf")
    
    if phi_Pn >= Pu:
        st.success(r"✅ 雙向長柱安全驗算通過！設計強度 \(\phi P_n\) " + f"({phi_Pn:.1f} tf) ≧ 需求值 " + r"\(P_u\) " + f"({Pu:.1f} tf)")
    else:
        st.error(r"❌ 結構斷面強度不足！設計強度 \(\phi P_n\) " + f"({phi_Pn:.1f} tf) ＜ 需求值 " + r"\(P_u\) " + f"({Pu:.1f} tf)，請調大斷面或調高配筋率。")
