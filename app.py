import streamlit as st
import numpy as np
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(page_title="湖南园区光储充现货交易风险量化模型", layout="wide")
st.title("⚡ 湖南省园区综合能源电价与现货交易风险量化模型 (专家版 v1.2)")
st.caption("v1.2 升级：支持零基装机容量 ｜ 修复图表万元量纲失真 ｜ 消除蒙特卡洛双重惩罚 ｜ 湖南'两个细则'与发改529号文合规校准")
st.markdown("---")

# ================= 侧边栏：园区参数（湖南园区） =================
st.sidebar.header("📊 园区参数设定")

st.sidebar.subheader("1. 物理资产与需量管理")
trans_cap = st.sidebar.slider("变压器容量 (kVA)", 1000, 20000, 8000, 500)
current_demand = st.sidebar.slider("当前月均申报需量 (kW)", 1000, 15000, 5000, 250)
demand_reduction = st.sidebar.slider("需量压降目标 (kW)", 0, 2000, 800, 50)
demand_price = st.sidebar.slider("需量电费单价 (元/kW·月)", 20.0, 60.0, 35.4, 0.5)
park_total_elec = st.sidebar.slider("年总用电量 (万kWh/年)", 500, 20000, 4500, 500)

# 【已修改】光伏、储能、充电桩装机容量最低值均设置为 0
pv_cap = st.sidebar.slider("光伏装机 (MW)", 0.0, 20.0, 6.0, 0.5)
ess_cap = st.sidebar.slider("储能装机 (MWh)", 0.0, 50.0, 15.0, 1.0)
ess_cycle = st.sidebar.slider("储能日循环次数", 0.5, 2.5, 1.9, 0.1)
ev_cap = st.sidebar.slider("充电桩装机 (kW)", 0, 10000, 4000, 500)
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
annual_factor = st.sidebar.slider("年化折算系数 (汛期弃光/受阻折减)", 0.60, 1.00, 0.80, 0.05)
ice_pv_drop = st.sidebar.slider("冰冻周光伏出力骤降 (%)", 0, 90, 60, 5) / 100.0
ice_price_surge = st.sidebar.slider("冰冻周现货电价飙升 (%)", 0, 150, 60, 5) / 100.0

st.sidebar.markdown("---")
st.sidebar.info("💡 专家提示：依据发改价格〔2023〕529号文，两部制电价需量核定下限为变压器容量的40%；湖南现货中长期差价合约（CfD）是抵御汛期水电下行与枯期上行波动的核心避险工具。")

# ================= 财务与工程常量 =================
PV_HOURS = 1000.0                      # 湖南年等效利用小时数典型值
LOAN_RATIO, LOAN_RATE, LOAN_TERM = 0.70, 0.045, 10 # 匹配当前项目贷款市场实际利率(~4.5%)
PV_COST, ESS_COST, EV_COST = 280.0, 70.0, 700.0    # 光伏280万/MW(2.8元/W), 储能70万/MWh(0.7元/Wh), 充电桩700元/kW
EV_HOURS, EV_FEE = 3.0, 0.45           # 每日等效利用小时, 充电服务费单价(元/kWh)

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

    if pv_cap > 0:
        pv_curve = np.maximum(0, np.sin((h - 6) * np.pi / 12))
        pv_gen = pv_cap * 1000 * pv_curve * 0.85
        forecast = pv_gen
        actual = pv_gen * np.maximum(0, (1 + np.random.normal(0, deviation_sigma, hours)))

        deviation = np.abs(actual - forecast)
        penalized = np.maximum(0, deviation - forecast * deviation_threshold)
        penalty = penalized * spot_prices * penalty_multiplier

        cfd_rev = forecast * cfd_ratio * cfd_price
        spot_rev = actual * (1 - cfd_ratio) * spot_prices
    else:
        cfd_rev = np.zeros(hours)
        spot_rev = np.zeros(hours)
        penalty = np.zeros(hours)

    return spot_prices, cfd_rev, spot_rev, penalty

spot_prices, cfd_rev, spot_rev, penalty = simulate_spot()
total_rev = cfd_rev.sum() + spot_rev.sum()
total_penalty = penalty.sum()
net_rev_30d = total_rev - total_penalty

# 年化偏差罚款 (万元)
dev_penalty_annual_wan = (total_penalty * (365 / 30)) / 10000.0

# ================= 20年全投资现金流模型 =================
def build_20y():
    lp = np.array([0.5,0.45,0.42,0.4,0.45,0.55,0.75,0.95,1.05,1.1,1.05,0.95,0.9,0.88,0.92,0.98,1.08,1.15,1.1,0.95,0.8,0.7,0.6,0.55])
    pc = np.array([0,0,0,0,0,0.05,0.15,0.35,0.65,0.85,0.98,1.0,0.95,0.98,0.85,0.6,0.3,0.15,0.05,0,0,0,0,0])
    h24 = np.arange(24)
    hourly_load = lp / lp.sum() * (park_total_elec * 10000 / 365)
    pv_share = pc / pc.sum()
    charge_mask = (h24 <= 5) | ((h24 >= 12) & (h24 <= 13))

    capex = pv_cap * PV_COST + ess_cap * ESS_COST + (ev_cap * EV_COST / 10000.0)
    loan = capex * LOAN_RATIO
    if loan > 0 and LOAN_RATE > 0:
        k = LOAN_RATE * (1 + LOAN_RATE) ** LOAN_TERM / ((1 + LOAN_RATE) ** LOAN_TERM - 1)
        annual_payment = loan * k
    else:
        annual_payment = 0.0

    # 需量管理计算 (严格遵守 40% 变压器容量保底规则)
    demand_floor = trans_cap * 0.4
    max_allowable_reduction = max(0.0, current_demand - demand_floor)
    actual_red = min(float(demand_reduction), max_allowable_reduction)
    demand_rev = actual_red * demand_price * 12 / 10000.0

    # 充电桩服务费收益 (万元)
    ev_rev = (ev_cap * EV_HOURS * EV_FEE * 335 / 10000.0) if ev_cap > 0 else 0.0

    # 峰谷加权价差
    weighted_spread = (8 / 12) * spread_normal + (4 / 12) * spread_peak

    cum, cum_share, payback, cum_list = 0.0, 0.0, None, []
    
    # 动态运维费用：随配置资产线性变动，无设备时不产生虚假高额运维费
    om_cost = (pv_cap * 3.5) + (ess_cap * 1.5) + (ev_cap * EV_COST / 10000.0 * 0.02) + (5.0 if capex > 0 else 0.0)

    for y in range(1, 21):
        deg_pv = (1 - pv_deg / 100.0) ** (y - 1) if pv_cap > 0 else 0.0
        deg_ess = (1 - ess_deg / 100.0) ** (y - 1) if ess_cap > 0 else 0.0
        
        # 光伏收益 (自发自用 + 余电入市上网)
        if pv_cap > 0:
            pv_h = pv_cap * 1000 * (PV_HOURS / 365.0) * deg_pv * pv_share
            self_use = np.minimum(pv_h, hourly_load)
            export = np.minimum(np.maximum(0.0, pv_h - hourly_load), trans_cap * 0.5)
            export_price = cfd_ratio * cfd_price + (1 - cfd_ratio) * spot_mean
            y_pv_rev = ((self_use * price_flat).sum() + (export * export_price).sum()) * 365.0 / 10000.0
        else:
            self_use = np.zeros(24)
            y_pv_rev = 0.0

        # 储能充放套利收益
        if ess_cap > 0:
            max_charge = np.sum(np.where(charge_mask, np.minimum(ess_cap * 500.0, np.maximum(0.0, trans_cap * 0.9 - hourly_load + self_use)), 0.0))
            max_discharge = np.sum(np.where(~charge_mask, np.minimum(hourly_load - self_use, ess_cap * 500.0), 0.0))
            actual_ess = min(ess_cap * 1000.0 * ess_cycle * 0.85 * deg_ess, max_discharge, max_charge * 0.85)
            y_ess_rev = actual_ess * 330.0 * weighted_spread / 10000.0
        else:
            y_ess_rev = 0.0

        gross = (y_pv_rev + y_ess_rev) * annual_factor + demand_rev + ev_rev
        net_full = gross - om_cost - dev_penalty_annual_wan
        cum += net_full
        cum_list.append(cum)

        if payback is None and capex > 0 and cum >= capex:
            payback = y
        cum_share += net_full - (annual_payment if y <= LOAN_TERM else 0.0)

    if capex == 0:
        payback_display = "无新增资产"
    elif payback is not None:
        payback_display = f"{payback} 年"
    else:
        payback_display = "超20年"

    return capex, payback_display, cum / 20.0, cum_share, cum_list, y_pv_rev, y_ess_rev, demand_rev, ev_rev, om_cost

capex, payback_display, avg_net, cum_share, cum_list, y_pv, y_ess, y_dem, y_ev, om_cost = build_20y()

# ================= 蒙特卡洛 VaR 与冰冻周压力测试 =================
np.random.seed(7)
# 修正：避免重复乘入 penalty_multiplier
mc = [(total_rev * np.random.normal(1, 0.15)) - (total_penalty * abs(np.random.normal(1, 0.3))) for _ in range(2000)]
mc = np.array(mc) / 10000.0 # 30天模拟期净收益 (万元)
p5 = np.percentile(mc, 5)
var95 = (net_rev_30d / 10000.0) - p5

# 冰冻周情景
F_week = pv_cap * 1000.0 * (PV_HOURS / 365.0) * 7.0
A_week = F_week * (1 - ice_pv_drop)
surge_price = np.clip(spot_mean * (1 + ice_price_surge), 0.0, 1.5)
ice_rev = A_week * cfd_ratio * cfd_price + A_week * (1 - cfd_ratio) * surge_price
ice_dev = np.maximum(0.0, (F_week - A_week) - deviation_threshold * F_week)
ice_penalty = ice_dev * surge_price * penalty_multiplier
ice_net = ice_rev - ice_penalty

ice_net_wan = ice_net / 10000.0
ice_penalty_wan = ice_penalty / 10000.0
normal_week = avg_net / 52.0
ice_shrink = ((normal_week - ice_net_wan) / normal_week * 100.0) if normal_week > 0 else 0.0

# ================= 前端可视化 =================
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("静态总投资", f"{capex:.1f} 万元")
r1c2.metric("全投资回本期", payback_display, "含年化衰减与偏差考核")
r1c3.metric("20年均税前净收益", f"{avg_net:.1f} 万元/年")
r1c4.metric("20年累计股东净现金流", f"{cum_share:.1f} 万元", "扣除70%贷款本息摊还")

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("偏差考核年罚款期望", f"{dev_penalty_annual_wan:.2f} 万元", "⚠️ 现货偏差敞口", delta_color="inverse")
r2c2.metric("30天 VaR95 风险价值", f"{var95:.2f} 万元", f"P5极端收益 {p5:.2f} 万", delta_color="inverse")
r2c3.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", "⚠️ 极端气象考验", delta_color="inverse")
r2c4.metric("冰冻周收益缩水幅度", f"{ice_shrink:.1f} %", delta_color="inverse")

st.markdown("### 📉 20年累计净现金流与投资回收轨迹")
# 【已修复】：直接使用万元单位，消除重复除以10000导致的失真
fig_cum = go.Figure(go.Scatter(
    x=list(range(1, 21)),
    y=cum_list,
    mode='lines+markers',
    name='累计净现金流',
    line=dict(color='#2563eb', width=2.5)
))
if capex > 0:
    fig_cum.add_hline(
        y=capex,
        line_dash="dash",
        line_color="red",
        annotation_text=f"初始总投资 ({capex:.1f} 万元)",
        annotation_position="bottom right"
    )
fig_cum.update_layout(
    height=380,
    xaxis_title="运营年份",
    yaxis_title="累计净现金流 (万元)",
    template="plotly_white",
    hovermode="x unified"
)
st.plotly_chart(fig_cum, use_container_width=True)

st.markdown("### 📈 湖南现货'鸭形曲线'与长协基准价对冲模拟")
fig_p = go.Figure(go.Scatter(y=spot_prices, mode='lines', name='现货节点日前电价', line=dict(color='#ef4444', width=1.2), opacity=0.7))
fig_p.add_hline(y=cfd_price, line_dash="dash", line_color="#16a34a", annotation_text=f"长协基准价 ({cfd_price}元/kWh)")
fig_p.add_hline(y=price_valley, line_dash="dot", line_color="#f59e0b", annotation_text=f"午间低谷电价 ({price_valley}元/kWh)")
fig_p.update_layout(height=380, xaxis_title="模拟小时 (连续30天)", yaxis_title="电价 (元/kWh)", template="plotly_white")
st.plotly_chart(fig_p, use_container_width=True)

st.markdown("### 🌀 冰冻周极端压力测试 (湖南冬季特色)")
st.caption("情景模拟：日前按常态申报出力，冰冻周光伏覆冰出力骤降，冬季紧供导致实时现货价格飙升，超免考核死区偏差按飙升电价×惩罚倍数结算。")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("常态周均净收益", f"{normal_week:.2f} 万元")
sc2.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", delta_color="inverse")
sc3.metric("冰冻周偏差罚款", f"{ice_penalty_wan:.2f} 万元", delta_color="inverse")

fig_ice = go.Figure(go.Bar(
    x=['常态周均净收益', '冰冻周净收益', '冰冻周偏差考核罚款'],
    y=[normal_week, ice_net_wan, ice_penalty_wan],
    marker_color=['#16a34a', '#dc2626', '#f59e0b'],
    text=[f"{normal_week:.2f}万", f"{ice_net_wan:.2f}万", f"{ice_penalty_wan:.2f}万"],
    textposition='auto'
))
fig_ice.update_layout(height=350, yaxis_title="金额 (万元)", template="plotly_white")
st.plotly_chart(fig_ice, use_container_width=True)

st.markdown("### ⚖️ 首年收益构成与扣减瀑布图")
fig_w = go.Figure(go.Waterfall(
    name="年度收益流",
    orientation="v",
    measure=["relative", "relative", "relative", "relative", "relative", "relative", "total"],
    x=['光伏收益', '储能套利', '需量管理', '充电服务', '运维成本', '偏差罚款', '年度净收益'],
    y=[y_pv, y_ess, y_dem, y_ev, -om_cost, -dev_penalty_annual_wan, (y_pv + y_ess + y_dem + y_ev - om_cost - dev_penalty_annual_wan)],
    connector={"line": {"color": "rgb(63, 63, 63)"}}
))
fig_w.update_layout(title="年度首年收益与成本构成分解 (万元)", template="plotly_white")
st.plotly_chart(fig_w, use_container_width=True)

st.markdown("### 🌪️ 极端行情蒙特卡洛概率分布 (30天期)")
fig_mc = go.Figure(go.Histogram(x=mc, nbinsx=50, marker_color='#2563eb', opacity=0.75))
fig_mc.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="盈亏平衡线 (0万元)")
fig_mc.add_vline(x=p5, line_dash="dot", line_color="orange", annotation_text=f"P5分位数 ({p5:.2f}万元)")
fig_mc.update_layout(title="30天模拟期净收益概率分布直方图 (万元)", xaxis_title="净收益 (万元)", yaxis_title="频数", template="plotly_white")
st.plotly_chart(fig_mc, use_container_width=True)

# ================= 专家策略与法律边界分析报告 =================
st.markdown("---")
st.header("📜 专家策略与法律边界分析报告（湖南版）")

st.subheader("1. 长协（CfD）与现货敞口对冲策略")
if cfd_ratio >= 0.70:
    st.success(f"**✅ 稳健型对冲**：中长期长协锁定比例达 **{cfd_ratio*100:.0f}%**。湖南具有典型的'丰水期水电挤压导致光伏弃光降价、枯水期火电边际成本推高电价'特征，高比例长协基准价（{cfd_price}元/kWh）能够有效屏蔽汛期现货负电价或低谷电价击穿成本线的风险。")
else:
    st.warning(f"**⚠️ 激进型敞口**：当前长协锁定比例仅为 **{cfd_ratio*100:.0f}%**。在湖南汛期及新能源大发时段，日前现货极易产生极低电价，建议将工商业项目长协签约比例提升至 70%~85%，同时配合配储平抑现货偏差。")

st.subheader("2. 偏差考核量化与'两个细则'合规应对")
st.error(f"**风险警示**：当前参数下年化偏差考核罚款期望为 **{dev_penalty_annual_wan:.2f} 万元**；在极端冰冻周情景下单周罚款达 **{ice_penalty_wan:.2f} 万元**。")
st.markdown("""
* **技术平抑**：配置 AI 超短期功率预测系统（将日前预测误差控制在死区内），并利用储能系统进行毫秒/分钟级充放电跟踪补偿。
* **规则救济**：熟练运用《湖南电力系统并网发电厂辅助服务管理实施细则》，发生不可抗力冰冻灾害时，应在规定时限内向湖南电力调度控制中心提交气象证明与不可抗力免考核申诉。
""")

st.subheader("3. 法律边界与 EMC / 绿电购销合同合规要点")
st.info("**⚖️ 综合能源项目法务风险管控清单**")
st.markdown("""
1. **需量管理 40% 刚性红线**：根据《国家发展改革委关于第三监管周期省级电网输配电价及有关事项的通知》（发改价格〔2023〕529号），申报最大需量不得低于变压器容量的 40%。EMC 合同中需约定：因业主负荷非受控骤降导致未达 40% 触发最低核定需量的基本电费，由业主方承担。
2. **电网反向受阻与弃光免责**：针对湖南部分地区电网承载力红黄预警、消纳受限导致的被动限电，EMC 合同必须约定该电量视同自发自用结算或计入不可抗力豁免条款，防止投资方遭受履约违约追索。
3. **极端冰冻天气法定免责条款**：在并网协议与购售电合同中明确约定湖南冬季雨雪冰冻、导线覆冰引发的出力受阻属于《民法典》第一百八十条规定的不可抗力，并设定与气象预警等级联动的免责机制。
4. **新型储能与虚拟电厂（VPP）聚合资质**：用户侧储能如参与湖南辅助服务市场（调峰/需求响应），应在合同中明确主体排他性授权、收益分配比例及调度指令执行不当的过错责任划分。
""")

st.markdown("---")
st.caption("⚖️ 免责声明：本模型基于蒙特卡洛随机模拟及湖南省典型能源监管电价政策构建，测算结果供投资论证及风险对冲参考，不构成法定收益承诺。实际结算数据以湖南电力交易中心正式出具的结算单及电网调度指令为准。")
