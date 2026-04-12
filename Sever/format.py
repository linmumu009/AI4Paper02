import streamlit as st
import pandas as pd
import json
import re
import plotly.express as px
from pathlib import Path
from textwrap import dedent

# ==========================================
# 0. 全局配置 (必须在第一行)
# ==========================================
st.set_page_config(page_title="DeepSearch Pro", page_icon="🧬", layout="wide")

# 初始化主题状态
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = 'dark'  # 默认深色，比较酷

def toggle_theme():
    st.session_state.theme_mode = 'light' if st.session_state.theme_mode == 'dark' else 'dark'

# ==========================================
# 1. 动态 CSS 设计系统 (Design System)
# ==========================================
# 这里定义了两套配色方案，不再使用纯黑纯白
if st.session_state.theme_mode == 'dark':
    # === 🌑 夜间模式 (Dark) ===
    css_vars = """
        --bg-color: #0b0f14;           /* 页面背景：深石墨 */
        --card-bg: #141a22;            /* 卡片背景：蓝灰 */
        --text-main: #e6e8ec;          /* 主文字：雾白 */
        --text-sub: #9aa3b2;           /* 副文字：蓝灰 */
        --border: #273042;             /* 边框：冷灰 */
        --accent: #2dd4bf;             /* 提亮色：青绿 */
        --tag-bg: #1a2330;             /* 标签背景 */
        --success-bg: rgba(34, 197, 94, 0.18);  /* 成功色背景 */
        --success-text: #22c55e;       /* 成功色文字 */
        --danger-bg: rgba(244, 63, 94, 0.18);   /* 警告色背景 */
        --danger-text: #f43f5e;        /* 警告色文字 */
        --shadow: 0 12px 30px rgba(0, 0, 0, 0.32);
        --ring: rgba(45, 212, 191, 0.35);
        --button-text: #0b1218;
        --bg-gradient: radial-gradient(1200px 600px at 15% -10%, rgba(45, 212, 191, 0.12), transparent 60%), radial-gradient(900px 500px at 85% 0%, rgba(59, 130, 246, 0.12), transparent 55%), var(--bg-color);
    """
    plot_template = "plotly_dark" # 图表主题
else:
    # === ☀️ 日间模式 (Light) ===
    css_vars = """
        --bg-color: #f4f2ed;           /* 页面背景：暖象牙 */
        --card-bg: #ffffff;            /* 卡片背景：纸白 */
        --text-main: #1f2937;          /* 主文字：深炭灰 */
        --text-sub: #667085;           /* 副文字：温灰 */
        --border: #e3ddd4;             /* 边框：砂岩灰 */
        --accent: #0f766e;             /* 提亮色：墨绿 */
        --tag-bg: #efebe2;             /* 标签背景 */
        --success-bg: #dcfce7;         /* 成功色背景 */
        --success-text: #15803d;       /* 成功色文字 */
        --danger-bg: #fee2e2;          /* 警告色背景 */
        --danger-text: #b91c1c;        /* 警告色文字 */
        --shadow: 0 18px 36px rgba(15, 23, 42, 0.08);
        --ring: rgba(15, 118, 110, 0.25);
        --button-text: #f8fafc;
        --bg-gradient: radial-gradient(1100px 500px at 10% -10%, rgba(15, 118, 110, 0.12), transparent 60%), radial-gradient(900px 500px at 85% -5%, rgba(37, 99, 235, 0.10), transparent 55%), var(--bg-color);
    """
    plot_template = "plotly_white" # 图表主题

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,700&family=Sora:wght@400;500;600&display=swap');

    :root {{
        {css_vars}
        --font-sans: "Sora", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
        --font-serif: "Newsreader", "Noto Serif SC", "Songti SC", serif;
    }}

    /* === 核心布局修正 === */
    
    /* 1. 给顶部留出空间，防止 Deploy 按钮遮挡 */
    .block-container {{
        padding-top: 4rem !important;
        padding-bottom: 5rem !important;
    }}

    /* 2. 强制应用背景色 */
    .stApp {{
        background: var(--bg-gradient) !important;
        color: var(--text-main) !important;
        font-family: var(--font-sans) !important;
    }}

    /* 3. 标题与文字颜色强制统一 */
    h1, h2, h3, h4, h5, h6 {{
        color: var(--text-main) !important;
        font-family: var(--font-serif) !important;
        letter-spacing: 0.2px;
    }}
    p, span, div, label {{
        color: var(--text-main) !important;
    }}
    
    /* 4. 链接样式 */
    a {{ color: var(--accent) !important; text-decoration: none; transition: 0.2s; }}
    a:hover {{ opacity: 0.8; text-decoration: underline; }}

    /* 5. 修复表格在日间模式下的背景 (让它不突兀) */
    div[data-testid="stDataFrame"] {{
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
        background: var(--card-bg) !important;
    }}

    div[data-testid="stDataFrame"] * {{
        color: var(--text-main) !important;
    }}
    
    /* 6. 按钮样式微调 */
    button[kind="primary"] {{
        background-color: var(--accent) !important;
        color: var(--button-text) !important;
        border: 1px solid transparent !important;
        box-shadow: var(--shadow);
        transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    }}
    button[kind="primary"]:hover {{
        transform: translateY(-1px);
        opacity: 0.9;
    }}
    button[kind="primary"]:focus-visible {{
        box-shadow: 0 0 0 3px var(--ring);
    }}

    /* 7. 输入控件统一质感 */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    input {{
        background: var(--card-bg) !important;
        border-color: var(--border) !important;
        color: var(--text-main) !important;
        border-radius: 10px !important;
    }}

    div[data-baseweb="input"] input::placeholder,
    textarea::placeholder {{
        color: var(--text-sub) !important;
    }}

    /* 8. Radio/Select 文案 */
    div[role="radiogroup"] label span {{
        color: var(--text-main) !important;
    }}

    /* ============================================ */
    /* 9. 自定义数据表格 — 完整设计                    */
    /* ============================================ */

    .ds-table-wrap {{
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
        box-shadow: var(--shadow);
    }}

    .ds-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 0.88em;
    }}

    /* --- 表头 --- */
    .ds-table thead th {{
        background: var(--tag-bg) !important;
        color: var(--text-sub) !important;
        font-weight: 600 !important;
        font-size: 0.78em !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
        padding: 14px 16px !important;
        border-bottom: 2px solid var(--border) !important;
        text-align: left !important;
        white-space: nowrap !important;
        position: sticky;
        top: 0;
        z-index: 2;
    }}

    /* --- 行 --- */
    .ds-table tbody tr {{
        transition: background-color 0.15s ease, box-shadow 0.15s ease;
    }}

    .ds-table tbody tr:nth-child(even) {{
        background-color: var(--card-bg);
    }}

    .ds-table tbody tr:nth-child(odd) {{
        background-color: var(--tag-bg);
    }}

    .ds-table tbody tr:hover {{
        background-color: color-mix(in srgb, var(--accent) 8%, var(--card-bg)) !important;
        box-shadow: inset 3px 0 0 var(--accent);
    }}

    /* --- 单元格 --- */
    .ds-table td {{
        padding: 14px 16px !important;
        border-bottom: 1px solid var(--border) !important;
        color: var(--text-main) !important;
        vertical-align: top !important;
        line-height: 1.55 !important;
    }}

    .ds-table tbody tr:last-child td {{
        border-bottom: none !important;
    }}

    /* --- ID 胶囊 --- */
    .ds-id {{
        font-family: 'Menlo', 'Consolas', monospace;
        font-size: 0.82em;
        color: var(--text-sub);
        background: var(--tag-bg);
        padding: 3px 8px;
        border-radius: 6px;
        white-space: nowrap;
    }}

    /* --- 类型徽章 --- */
    .ds-badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.78em;
        font-weight: 600;
        white-space: nowrap;
    }}
    .ds-badge-success {{
        color: var(--success-text);
        background: var(--success-bg);
    }}
    .ds-badge-danger {{
        color: var(--danger-text);
        background: var(--danger-bg);
    }}
    .ds-badge-neutral {{
        color: var(--text-sub);
        background: var(--tag-bg);
    }}

    /* --- 标题链接 --- */
    .ds-title-link {{
        font-weight: 500;
        line-height: 1.5;
        color: var(--text-main) !important;
        text-decoration: none !important;
        transition: color 0.2s;
    }}
    .ds-title-link:hover {{
        color: var(--accent) !important;
        text-decoration: none !important;
    }}

    /* --- 结果指标条 --- */
    .ds-metrics {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }}
    .ds-metric-chip {{
        font-family: 'Menlo', 'Consolas', monospace;
        font-size: 0.82em;
        color: var(--text-sub);
        background: var(--tag-bg);
        padding: 3px 9px;
        border-radius: 6px;
        white-space: nowrap;
        border: 1px solid var(--border);
    }}
    .ds-metric-chip b {{
        color: var(--accent) !important;
        font-weight: 600;
    }}

    /* --- 机制列 --- */
    .ds-mech {{
        font-size: 0.9em;
        color: var(--text-sub);
        max-width: 260px;
    }}

    /* --- 链接按钮 --- */
    .ds-link-btn {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 8px;
        background: var(--tag-bg);
        color: var(--accent) !important;
        text-decoration: none !important;
        transition: background 0.15s, transform 0.15s;
        font-size: 1em;
    }}
    .ds-link-btn:hover {{
        background: color-mix(in srgb, var(--accent) 18%, var(--tag-bg));
        transform: scale(1.1);
        text-decoration: none !important;
    }}

    /* 10. 底部 expander 内 st.dataframe 精修 */
    div[data-testid="stExpander"] div[data-testid="stDataFrame"] {{
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        background: var(--card-bg) !important;
    }}

</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 数据处理逻辑 (保持稳健)
# ==========================================
@st.cache_data
def load_data(file_path):
    records = []
    path = Path(file_path)
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: records.append(json.loads(line))
                except: continue
    return records

def parse_data_v2(records):
    main_rows = []
    results_all_rows = []
    methods_all_rows = []

    for paper in records:
        pid = paper.get("paper_id")
        title = paper.get("title")
        url = paper.get("url")
        blocks = paper.get("blocks", {})

        # Method Parsing — new 13-key schema uses sub-fields directly;
        # fall back to parsing old bullets format for legacy data.
        method_block = blocks.get("method", {})
        method_data = {"ID": pid, "Title": title, "URL": url}

        # New schema: use structured sub-fields when available
        for sub_key, label in [
            ("input",                   "输入"),
            ("task_or_object",          "对象/任务"),
            ("architecture_or_paradigm","架构"),
            ("key_mechanisms",          "关键机制"),
            ("training_required",       "是否训练"),
            ("training_or_optimization","训练/优化"),
            ("inference_strategy",      "推理策略"),
            ("novelty",                 "创新点"),
        ]:
            val = method_block.get(sub_key)
            if val:
                if isinstance(val, list):
                    method_data[label] = "；".join(str(v) for v in val if v)
                else:
                    method_data[label] = str(val)

        # Legacy fallback: parse 【key】：value from bullets
        if not any(k in method_data for k in ("是否训练", "架构", "关键机制")):
            for b in method_block.get("bullets", []):
                m = re.match(r"^\s*【(.*?)】[：:]\s*(.*)$", b)
                if m:
                    method_data[m.group(1).strip()] = m.group(2).strip()

        train_status = str(method_data.get("是否训练", ""))
        if "否" in train_status or "No" in train_status.lower():
            type_tag = "🟢 免训练"
            css_class = "success"
        elif "是" in train_status or "yes" in train_status.lower():
            type_tag = "🔴 需训练"
            css_class = "danger"
        else:
            type_tag = "⚪ 未知"
            css_class = "neutral"

        method_data["Type_Tag"] = type_tag
        method_data["CSS_Class"] = css_class
        methods_all_rows.append(method_data)

        # Result Parsing — new schema: use numerical_results list directly;
        # fall back to regex parsing on old bullets for legacy data.
        results_block = blocks.get("results", {})
        paper_res_strs = []

        # New schema: numerical_results list (format: "task: metric = value")
        num_results = results_block.get("numerical_results", [])
        parsed_from_subfield = False
        for entry in (num_results or []):
            m = re.search(r"(.*?)[：:](.*?)[=≈]\s*([\d\.]+%?)", str(entry))
            if m:
                task = m.group(1).strip()
                metric = m.group(2).strip()
                score_str = m.group(3).strip()
                try:
                    score_val = float(score_str.replace('%', '').replace('+', ''))
                except ValueError:
                    score_val = 0.0
                results_all_rows.append({
                    "ID": str(pid),
                    "Title": title, "Type_Tag": type_tag, "Task": task,
                    "Metric": metric, "Score_Raw": score_str, "Score_Val": score_val,
                    "Raw_Text": entry,
                })
                paper_res_strs.append(f"{task}: {score_str}")
                parsed_from_subfield = True

        # Legacy fallback: parse bullets when numerical_results is absent
        if not parsed_from_subfield:
            for b in results_block.get("bullets", []):
                m = re.search(r"(.*?)[：:](.*?)[=≈]\s*([\d\.]+%?)", b)
                if m:
                    task = m.group(1).strip()
                    metric = m.group(2).strip()
                    score_str = m.group(3).strip()
                    try:
                        score_val = float(score_str.replace('%', '').replace('+', ''))
                    except ValueError:
                        score_val = 0.0
                    results_all_rows.append({
                        "ID": str(pid),
                        "Title": title, "Type_Tag": type_tag, "Task": task,
                        "Metric": metric, "Score_Raw": score_str, "Score_Val": score_val,
                        "Raw_Text": b,
                    })
                    paper_res_strs.append(f"{task}: {score_str}")

        main_row = method_data.copy()
        main_row["All_Results_Str"] = "\n".join(paper_res_strs) if paper_res_strs else "暂无数据"
        main_rows.append(main_row)

    return pd.DataFrame(main_rows), pd.DataFrame(results_all_rows), pd.DataFrame(methods_all_rows)


# ==========================================
# 3. 页面内容渲染
# ==========================================
data_file = "data/paper_assets/2026-02-07.jsonl"
records = load_data(data_file)
if not records:
    st.error(f"⚠️ 数据文件未找到: {data_file}")
    st.stop()

df_main, df_results_all, df_methods_all = parse_data_v2(records)

# --- Header 区 (标题 + 模式切换) ---
c1, c2 = st.columns([8, 1])

with c1:
    st.title("🧬 DeepSearch 科研指挥舱")
    st.caption(f"已收录 {len(df_main)} 篇论文 | 追踪 {len(df_results_all)} 组 SOTA 数据")

with c2:
    # 切换按钮放在这里，并增加了 padding-top 防止被遮挡
    st.write("") # 占位
    btn_label = "🌞 日间" if st.session_state.theme_mode == 'dark' else "🌙 夜间"
    if st.button(btn_label, use_container_width=True, type="primary"):
        toggle_theme()
        st.rerun()

# --- 筛选与视图 ---
with st.container():
    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True) # 增加一点间距
    
    col_filter, col_search = st.columns([2, 5])
    with col_filter:
        view_mode = st.radio("视图模式", ["📱 卡片流 (Mobile)", "🖥️ 战术大表 (Desktop)"], horizontal=True, label_visibility="collapsed")
    with col_search:
        search_q = st.text_input("全局搜索", placeholder="🔍 搜索论文标题、机制、ID...", label_visibility="collapsed")

if search_q:
    mask = df_main.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)
    df_main_show = df_main[mask]
else:
    df_main_show = df_main

# --- 视图渲染 ---
st.markdown("---")

if "战术大表" in view_mode:
    # === 自定义 HTML 表格渲染 ===
    def _badge_html(tag: str) -> str:
        if "免训练" in tag:
            return f'<span class="ds-badge ds-badge-success">{tag}</span>'
        elif "需训练" in tag:
            return f'<span class="ds-badge ds-badge-danger">{tag}</span>'
        return f'<span class="ds-badge ds-badge-neutral">{tag}</span>'

    def _metrics_html(raw: str) -> str:
        if not raw or raw == "暂无数据":
            return '<span style="color:var(--text-sub); font-size:0.85em;">暂无数据</span>'
        chips = []
        for item in raw.split("\n"):
            item = item.strip()
            if not item:
                continue
            # 分离 "Task: Score"
            if ":" in item:
                parts = item.split(":", 1)
                chips.append(f'<span class="ds-metric-chip">{parts[0].strip()}:&nbsp;<b>{parts[1].strip()}</b></span>')
            else:
                chips.append(f'<span class="ds-metric-chip">{item}</span>')
        return '<div class="ds-metrics">' + "".join(chips) + "</div>"

    rows_html = []
    for _, row in df_main_show.iterrows():
        url = row.get("URL", "#")
        rows_html.append(f"""<tr>
<td><span class="ds-id">#{row['ID']}</span></td>
<td>{_badge_html(row['Type_Tag'])}</td>
<td><a class="ds-title-link" href="{url}" target="_blank">{row['Title']}</a></td>
<td>{_metrics_html(row.get('All_Results_Str', ''))}</td>
<td><span class="ds-mech">{row.get('关键机制', 'N/A')}</span></td>
<td style="text-align:center;"><a class="ds-link-btn" href="{url}" target="_blank">🔗</a></td>
</tr>""")

    table_html = f"""<div class="ds-table-wrap"><table class="ds-table">
<thead><tr>
<th style="width:80px;">ID</th>
<th style="width:100px;">类型</th>
<th>标题</th>
<th style="width:280px;">实验结果</th>
<th style="width:220px;">核心机制</th>
<th style="width:56px;text-align:center;">链接</th>
</tr></thead>
<tbody>{"".join(rows_html)}</tbody>
</table></div>"""
    st.markdown(table_html, unsafe_allow_html=True)

elif "卡片流" in view_mode:
    # === 卡片流设计 (Design Master Class) ===
    # 这里使用了我们上面定义的 CSS 变量，确保完美的自适应
    for _, row in df_main_show.iterrows():
        
        # 根据类型选择颜色变量
        status_color = "var(--success-text)" if "免训练" in row['Type_Tag'] else "var(--danger-text)"
        status_bg = "var(--success-bg)" if "免训练" in row['Type_Tag'] else "var(--danger-bg)"
        
        # 将换行转为 <br>，避免 dedent + pre-wrap 导致缩进错乱
        results_html = row.get('All_Results_Str', '暂无数据').replace('\n', '<br>')
        
        card_html = f"""<div style="
background-color: var(--card-bg);
border: 1px solid var(--border);
border-radius: 12px;
padding: 20px;
margin-bottom: 16px;
box-shadow: var(--shadow);
transition: transform 0.2s ease;
">
<div style="display:flex; justify-content:space-between; align-items:start; margin-bottom: 12px;">
<div style="font-family: monospace; font-size: 0.85em; color: var(--text-sub); background: var(--tag-bg); padding: 4px 8px; border-radius: 6px;">
#{row['ID']}
</div>
<div style="
color: {status_color};
background-color: {status_bg};
padding: 4px 10px;
border-radius: 20px;
font-size: 0.8em;
font-weight: 600;">
{row['Type_Tag']}
</div>
</div>
<h3 style="margin: 0 0 10px 0; font-size: 1.1em; line-height: 1.5;">
<a href="{row.get('URL', '#')}" target="_blank">
{row['Title']}
</a>
</h3>
<div style="margin-bottom: 12px; font-size: 0.95em; color: var(--text-main);">
<span style="color: var(--text-sub);">🔧 核心机制：</span>
{row.get('关键机制', 'N/A')}
</div>
<div style="
background-color: var(--tag-bg);
padding: 12px;
border-radius: 8px;
font-family: 'Menlo', 'Consolas', monospace;
font-size: 0.85em;
color: var(--text-sub);
line-height: 1.6;
">{results_html}</div>
</div>"""
        st.markdown(card_html, unsafe_allow_html=True)

# ==========================================
# 4. 图表修复区 (Fixed Charts)
# ==========================================
st.markdown("### 📊 学术图表分析")

if not df_results_all.empty:
    top_tasks = df_results_all["Task"].value_counts().head(10).index.tolist()
    c1, c2 = st.columns([1, 4])
    with c1:
        st.write("") # 对齐
        st.write("") 
        selected_task = st.selectbox("选择任务", top_tasks)
        metrics_series = df_results_all.loc[df_results_all["Task"] == selected_task, "Metric"].dropna()
        metrics_opts = list(pd.unique(metrics_series))
        selected_metric = st.selectbox("选择指标", metrics_opts) if len(metrics_opts) > 0 else None
    
    with c2:
        if selected_metric:
            chart_mask = (
                (df_results_all["Task"] == selected_task) & 
                (df_results_all["Metric"] == selected_metric)
            )
            chart_data = pd.DataFrame(df_results_all.loc[chart_mask])
            chart_data = chart_data.sort_values(by=["Score_Val"], ascending=False)
            
            if not chart_data.empty:
                # === 核心修复：强制转字符串 ===
                chart_data["ID"] = chart_data["ID"].astype(str)
                
                fig = px.bar(
                    chart_data, 
                    x="ID", 
                    y="Score_Val", 
                    color="Type_Tag", 
                    text="Score_Raw",
                    hover_data=["Title", "Raw_Text"],
                    title=f"{selected_task} - {selected_metric} 排行榜",
                    # 使用柔和的配色
                    color_discrete_map={"🟢 免训练": "#22c55e", "🔴 需训练": "#f43f5e", "⚪ 未知": "#94a3b8"},
                    template=plot_template # 跟随主题
                )
                
                # === 核心修复：强制分类轴 ===
                fig.update_xaxes(type='category', title_text="论文 ID") 
                fig.update_yaxes(title_text="分数")
                
                # 调整图表背景透明，完美融入
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", 
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(size=13),
                    bargap=0.3
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("该任务下暂无数据")
else:
    st.info("暂无数据")

# ==========================================
# 5. 底部数据表
# ==========================================
with st.expander("📑 查看完整原始数据", expanded=False):
    tab1, tab2 = st.tabs(["📈 实验数据", "🔬 方法参数"])
    with tab1: st.dataframe(df_results_all, use_container_width=True)
    with tab2: st.dataframe(df_methods_all, use_container_width=True)
