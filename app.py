import streamlit as st
import numpy as np
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(page_title="湖南园区光储充现货交易风险量化模型", layout="wide")
st.title("⚡ 湖南省园区综合能源电价与现货交易风险量化模型 (专家版 v1.1)")
st.caption("v1.1 修正：修复财务测算单位错配Bug (元/万元) ｜ 湖南'水火互济'情景 ｜ 冰冻周压力测试 ｜ CfD长协对冲 ｜ EMC法律边界")
st.markdown("---")

# ================= 侧边栏：园区参数（湖南园区） =================
st.sidebar.header("📊 园区参数设定")

st.sidebar.subheader("1. 物理资产与需量管理")
trans_cap = st.sidebar.slider("变压器容量 (kVA)", 1000, 20000, 8000, 500)
current_demand = st.sidebar.slider("当前月均申报需量 (kW)", 1000, 15000, 5000, 250)
demand_reduction = st.sidebar.slider("需量压降目标 (kW)", 0, 2000, 800, 50)
demand_price = st.sidebar.slider("需量电费单价 (元/kW·月)", 20.0, 60.0, 35.4, 0.5)
park_total_elec = st.sidebar.slider("年总用电量 (万kWh/年)", 1000, 20000, 4500, 500)
pv_cap = st.sidebar.slider("光伏装机 (MW)", 1.0, 20.0, 6.0, 0.5)
ess_cap = st.sidebar.slider("储能装机 (MWh)", 5.0, 50.0, 15.0, 1.0)
ess_cycle = st.sidebar.slider("储能日循环次数", 1.0, 2.5, 1.9, 0.1)
ev_cap = st.sidebar.slider("充电桩装机 (kW)", 500, 10000, 4000, 500)
pv_deg = st.sidebar.slider("光伏年衰减率 (%)", 0.1, 2.0, 0.5, 0.1)
ess_deg = st.sidebar.slider("储能年衰减率 (%)", 0.5, 5.0, 2.0, 0.5)

st.sidebar.subheader("2. 湖南分时电价与现货参数 (CfD对冲)")
spread_normal = st.sidebar.slider("常态峰谷价差 (元/kWh)", 0.3, 1.2, 0.824, 0.01)
spread_peak = st.sidebar.slider("尖峰峰谷价差 (元/kWh)", 0.5, 1.6, 1.08, 0.01)
price_flat = st.sidebar.slider("平段电价 (元/kWh)", 0.4, 1.0, 0.74, 0.01)
price_valley = st.sidebar.slider("午间低谷电价 (元/kWh)", 0.1, 0.6, 0.33, 0.01)
cfd_ratio = st.sidebar.slider("中长期长协锁定比例 (%)", 0, 100, 70, 5) / 100.0
cfd_price = st.sidebar.slider("长协基准价 (元/kWh)", 0.30, 0.60, 0.42, 0.01)
spot_mean = st.sidebar.slider("现货日前均价期望 (元/kWh)", 0.15, 0.55, 0.36, 0.01)
spot_sigma = st.sidebar.slider("现货价格波动率 (Sigma)", 0.05, 0.30, 0.15, 0.01)

st.sidebar.subheader("3. 偏差考核 (湖南'两个细则'/现货规则)")
deviation_sigma = st.sidebar.slider("光伏预测误差标准差 (%)", 2.0, 20.0, 8.0, 1.0) / 100.0
penalty_multiplier = st.sidebar.slider("偏差惩罚倍数 (实时电价)", 1.0, 3.0, 1.5, 0.1)
deviation_threshold = st.sidebar.slider("免考核死区 (%)", 0.0, 10.0, 3.0, 0.5) / 100.0

st.sidebar.subheader("4. 年化校准与冰冻周压力测试")
annual_factor = st.sidebar.slider("年化折算系数 (汛期弃光折减)", 0.60, 1.00, 0.80, 0.05)
ice_pv_drop = st.sidebar.slider("冰冻周光伏出力骤降 (%)", 0, 90, 60, 5) / 100.0
ice_price_surge = st.sidebar.slider("冰冻周现货电价飙升 (%)", 0, 150, 60, 5) / 100.0

st.sidebar.markdown("---")
st.sidebar.info("💡 专家提示：湖南电力'枯紧丰松'——冬季冰冻致出力骤降且电价飙升（罚款被放大），汛期水电挤压致弃光降价；午间低谷分时为储能提供套利空间。")

# ================= 常量 =================
PV_HOURS = 1000.0                      
LOAN_RATIO, LOAN_RATE, LOAN_TERM = 0.70, 0.068, 10
PV_COST, ESS_COST, EV_COST = 280.0, 70.0, 700.0   
EV_HOURS, EV_FEE = 3.0, 0.45           

# ================= 30天小时级现货模拟 =================
def simulate_spot(days=30):
    np.random.seed(42)
    hours = days * 24
    t = np.arange(hours)
    h = t % 24
    daily_cycle = (np.where((h >= 7) & (h <= 9), 0.10, 0) +
                   np.where((h >= 17) & (h <= 22), 0.18, 0) -
                   np.where((h >= 11) & (h <= 15), 0.12, 0))
    spot_prices = np.clip(spot_mean + daily_cycle + np.random.normal(0, spot_sigma, hours), 0.0, 1.5)

    pv_curve = np.maximum(0, np.sin((h - 6) * np.pi / 12))
    pv_gen = pv_cap * 1000 * pv_curve * 0.85
    forecast = pv_gen
    actual = pv_gen * (1 + np.random.normal(0, deviation_sigma, hours))

    deviation = np.abs(actual - forecast)
    penalized = np.maximum(0, deviation - forecast * deviation_threshold)
    penalty = penalized * spot_prices * penalty_multiplier

    cfd_rev = forecast * cfd_ratio * cfd_price
    spot_rev = actual * (1 - cfd_ratio) * spot_prices
    return spot_prices, cfd_rev, spot_rev, penalty

spot_prices, cfd_rev, spot_rev, penalty = simulate_spot()
total_rev = cfd_rev.sum() + spot_rev.sum()
total_penalty = penalty.sum()
net_rev = total_rev - total_penalty

# 【修复】将元转换为万元
dev_penalty_annual_wan = (total_penalty * (365 / 30)) / 10000 

# ================= 20年全投资现金流 =================
def build_20y():
    lp = np.array([0.5,0.45,0.42,0.4,0.45,0.55,0.75,0.95,1.05,1.1,1.05,0.95,0.9,0.88,0.92,0.98,1.08,1.15,1.1,0.95,0.8,0.7,0.6,0.55])
    pc = np.array([0,0,0,0,0,0.05,0.15,0.35,0.65,0.85,0.98,1.0,0.95,0.98,0.85,0.6,0.3,0.15,0.05,0,0,0,0,0])
    h24 = np.arange(24)
    hourly_load = lp / lp.sum() * (park_total_elec * 10000 / 365)
    pv_share = pc / pc.sum()
    charge_mask = (h24 <= 5) | ((h24 >= 12) & (h24 <= 13))

    capex = pv_cap * PV_COST + ess_cap * ESS_COST + ev_cap * EV_COST / 10000
    loan = capex * LOAN_RATIO
    k = LOAN_RATE * (1 + LOAN_RATE) ** LOAN_TERM / ((1 + LOAN_RATE) ** LOAN_TERM - 1)
    annual_payment = loan * k

    actual_red = min(demand_reduction, max(0.0, current_demand - trans_cap * 0.4))
    demand_rev = actual_red * demand_price * 12 / 10000
    ev_rev = ev_cap * EV_HOURS * EV_FEE * 335 / 10000
    weighted_spread = (8 / 12) * spread_normal + (4 / 12) * spread_peak

    cum, cum_share, payback, cum_list = 0.0, 0.0, None, []
    for y in range(1, 21):
        deg_pv = (1 - pv_deg / 100) ** (y - 1)
        deg_ess = (1 - ess_deg / 100) ** (y - 1)
        pv_h = pv_cap * 1000 * (PV_HOURS / 365) * deg_pv * pv_share
        self_use = np.minimum(pv_h, hourly_load)
        export = np.minimum(np.maximum(0, pv_h - hourly_load), trans_cap * 0.5)
        export_price = cfd_ratio * cfd_price + (1 - cfd_ratio) * spot_mean
        y_pv_rev = ((self_use * price_flat).sum() + (export * export_price).sum()) * 365 / 10000

        max_charge = np.sum(np.where(charge_mask, np.minimum(ess_cap * 500, np.maximum(0, trans_cap * 0.9 - hourly_load + self_use)), 0))
        max_discharge = np.sum(np.where(~charge_mask, np.minimum(hourly_load - self_use, ess_cap * 500), 0))
        actual_ess = min(ess_cap * 1000 * ess_cycle * 0.85 * deg_ess, max_discharge, max_charge * 0.85)
        y_ess_rev = actual_ess * 330 * weighted_spread / 10000

        gross = (y_pv_rev + y_ess_rev) * annual_factor + demand_rev + ev_rev
        # 【修复】统一使用万元单位扣减罚款
        net_full = gross - (pv_cap * 5 + 30) - dev_penalty_annual_wan 
        cum += net_full
        cum_list.append(cum)
        if payback is None and cum >= capex:
            payback = y
        cum_share += net_full - (annual_payment if y <= LOAN_TERM else 0.0)

    return capex, payback, cum / 20, cum_share, cum_list, y_pv_rev, y_ess_rev, demand_rev, ev_rev

capex, payback, avg_net, cum_share, cum_list, y_pv, y_ess, y_dem, y_ev = build_20y()

# ================= 蒙特卡洛 VaR 与冰冻周压力测试 =================
np.random.seed(7)
mc = [(total_rev * np.random.normal(1, 0.2)) - (total_penalty * abs(np.random.normal(1, 0.4)) * penalty_multiplier) for _ in range(2000)]
mc = np.array(mc) / 10000
p5 = np.percentile(mc, 5)
var95 = net_rev / 10000 - p5

F_week = pv_cap * 1000 * (PV_HOURS / 365) * 7
A_week = F_week * (1 - ice_pv_drop)
surge_price = np.clip(spot_mean * (1 + ice_price_surge), 0.0, 1.5)
ice_rev = A_week * cfd_ratio * cfd_price + A_week * (1 - cfd_ratio) * surge_price
ice_dev = np.maximum(0, (F_week - A_week) - deviation_threshold * F_week)
ice_penalty = ice_dev * surge_price * penalty_multiplier
ice_net = ice_rev - ice_penalty

# 【修复】统一转换为万元
ice_net_wan = ice_net / 10000
ice_penalty_wan = ice_penalty / 10000
normal_week = avg_net / 52
ice_shrink = (normal_week - ice_net_wan) / normal_week * 100 if normal_week > 0 else 0.0

# ================= 前端可视化 =================
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("静态总投资", f"{capex:.0f} 万元")
r1c2.metric("全投资回本期", f"{payback} 年" if payback else "超20年", "含校准与偏差考核")
r1c3.metric("20年均税前净利润", f"{avg_net:.0f} 万元/年")
r1c4.metric("20年累计股东净收益", f"{cum_share:.0f} 万元", "扣除70%贷款摊还")

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("偏差考核年罚款期望", f"{dev_penalty_annual_wan:.1f} 万元", "⚠️ 风险敞口", delta_color="inverse")
r2c2.metric("P5风险价值 (VaR95)", f"{var95:.2f} 万元", f"P5净收益 {p5:.1f} 万", delta_color="inverse")
r2c3.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", "⚠️ 罚款或超周收益", delta_color="inverse")
r2c4.metric("冰冻周收益缩水", f"{ice_shrink:.0f} %", delta_color="inverse")

st.markdown("### 📉 20年累计净现金流与回本轨迹")
fig_cum = go.Figure(go.Scatter(x=list(range(1, 21)), y=[c / 10000 for c in cum_list], mode='lines+markers', line=dict(color='#2563eb')))
fig_cum.add_hline(y=capex / 10000, line_dash="dash", line_color="red", annotation_text=f"总投资 {capex:.0f}万")
fig_cum.update_layout(height=380, xaxis_title="运营年份", yaxis_title="累计净现金流 (万元)", template="plotly_white")
st.plotly_chart(fig_cum, use_container_width=True)

st.markdown("### 📈 湖南现货'鸭形曲线'与长协基准价对冲效果图")
fig_p = go.Figure(go.Scatter(y=spot_prices, mode='lines', name='现货节点电价', line=dict(color='red', width=1), opacity=0.6))
fig_p.add_hline(y=cfd_price, line_dash="dash", line_color="green", annotation_text=f"长协基准价 ({cfd_price}元)")
fig_p.add_hline(y=price_valley, line_dash="dot", line_color="orange", annotation_text=f"午间低谷 ({price_valley}元)")
fig_p.update_layout(height=380, xaxis_title="时间 (小时)", yaxis_title="电价 (元/kWh)", template="plotly_white")
st.plotly_chart(fig_p, use_container_width=True)

st.markdown("### 🌀 冰冻周极端压力测试 (湖南特色)")
st.caption("情景：日前按正常天气申报，冰冻周光伏覆冰出力骤降，冬季紧供电价飙升，超死区偏差按飙升后实时电价×惩罚倍数考核。")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("正常周净收益", f"{normal_week:.2f} 万元")
sc2.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", delta_color="inverse")
sc3.metric("冰冻周偏差罚款", f"{ice_penalty_wan:.2f} 万元", delta_color="inverse")
fig_ice = go.Figure(go.Bar(x=['正常周净收益', '冰冻周净收益', '冰冻周偏差罚款'],
                           y=[normal_week, ice_net_wan, ice_penalty_wan],
                           marker_color=['#16a34a', '#dc2626', '#f59e0b']))
fig_ice.update_layout(height=350, yaxis_title="万元", template="plotly_white")
st.plotly_chart(fig_ice, use_container_width=True)

st.markdown("### ⚖️ 年度收益构成与偏差罚款瀑布图")
fig_w = go.Figure(go.Waterfall(
    x=['光伏收益', '储能套利', '需量管理', '充电服务', '偏差罚款(扣除)'],
    y=[y_pv, y_ess, y_dem, y_ev, -dev_penalty_annual_wan],
    connector={"line": {"color": "rgb(63, 63, 63)"}}))
fig_w.update_layout(title="年度现金流构成 (万元)", template="plotly_white")
st.plotly_chart(fig_w, use_container_width=True)

st.markdown("### 🌪️ 极端行情压力测试 (蒙特卡洛分布)")
fig_mc = go.Figure(go.Histogram(x=mc, nbinsx=50, marker_color='#2563eb'))
fig_mc.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="亏损警戒线")
fig_mc.add_vline(x=p5, line_dash="dot", line_color="orange", annotation_text="P5分位")
fig_mc.update_layout(title="模拟期净收益概率分布 (万元)", template="plotly_white")
st.plotly_chart(fig_mc, use_container_width=True)

# ================= 专家策略与法律边界分析报告 =================
st.markdown("---")
st.header("📜 专家策略与法律边界分析报告（湖南版）")

st.subheader("1. 长协与现货敞口对冲策略")
if cfd_ratio >= 0.7:
    st.success(f"**✅ 稳健型对冲**：长协锁定 **{cfd_ratio*100:.0f}%**，以长协基准价作为边际成本锚，有效屏蔽汛期水电挤压导致的现货价格下探；保留敞口捕捉枯水期/迎峰度冬电价上行收益。")
else:
    st.warning(f"**⚠️ 激进型敞口**：长协仅 **{cfd_ratio*100:.0f}%**。湖南汛期现货价格可能长期低于光伏全成本，建议提升至 70%-85%，并用储能滚动平抑偏差。")

st.subheader("2. 偏差考核风险量化与应对")
st.error(f"**风险警告**：偏差考核年罚款期望 **{dev_penalty_annual_wan:.1f} 万元**；冰冻周情景下罚款高达 **{ice_penalty_wan:.2f} 万元**（高实时电价放大惩罚）。应对：AI超短期功率预测（误差<3%）+ 储能实时平抑 + 依据湖南'两个细则'申请冰冻等极端天气考核豁免。")

st.subheader("3. 法律边界与 EMC 合同风险传导")
st.info("**⚖️ 湖南综合能源管理商合规提示**")
st.markdown("""
1. **冰冻/覆冰不可抗力免责**：湖南冬季冰冻属典型极端气象，EMC 及并网调度协议中须明确其作为《民法典》不可抗力及湖南'两个细则'考核豁免的触发阈值（如覆冰厚度、气象橙色预警）。
2. **汛期弃光豁免与补偿**：因水电挤压、电网断面受限导致的调度限电（弃光），应约定偏差免责及辅助服务/补偿分摊条款，管理商不得单方兜底。
3. **需量管理与风险传导**：两部制需量压降收益以变压器容量 40% 为法律/技术下限，合同中须载明申报需量调整须经业主书面确认。
4. **储能/ VPP 合规**：独立储能容量租赁、调峰补偿及虚拟电厂聚合参与湖南现货与辅助服务市场，须取得排他性调度授权并厘清与调度机构的责任边界。
""")

st.markdown("---")
st.caption("⚖️ 免责声明：本模型基于蒙特卡洛算法与湖南典型气象/电价参数推演，仅供商业决策参考，不构成投资收益保证；实际结算以湖南电力交易中心规则及电网调度指令为准。演示参数，实际项目请以可行性研究报告为准。")
