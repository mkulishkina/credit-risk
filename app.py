
import streamlit as st
import pandas as pd
import altair as alt
import math
import re
from html import escape
from datetime import datetime


def format_money(value):
    """Форматирует денежные суммы до целых: 60 000."""
    if pd.isna(value):
        return "—"
    return f"{value:,.0f}".replace(",", " ")


def parse_money(value):
    """Преобразует ввод вроде '60 000,00' в число."""
    text = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        raise ValueError("Пустое значение")

    # Если введены и точка, и запятая, последняя считается десятичным знаком.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")

    number = float(text)
    if not math.isfinite(number):
        raise ValueError("Сумма должна быть конечным числом")
    return number


def normalize_money_input(key):
    """После редактирования добавляет разделители разрядов в поле ввода."""
    try:
        value = parse_money(st.session_state[key])
        st.session_state[key] = format_money(value)
    except (ValueError, TypeError):
        pass


def money_input(label, default, key, container=st, min_value=0.0):
    """Поле ввода денежной суммы с пробелами между разрядами."""
    if key not in st.session_state:
        st.session_state[key] = format_money(default)

    raw_value = container.text_input(
        label,
        key=key,
        on_change=normalize_money_input,
        args=(key,),
        help="Можно вводить сумму с пробелами между разрядами, например 60 000."
    )

    try:
        value = parse_money(raw_value)
        if value < min_value:
            st.error(f"Поле «{label}»: значение не может быть меньше {format_money(min_value)} ₽. Исправьте сумму для продолжения расчёта.")
            st.stop()
        return value
    except (ValueError, TypeError):
        st.error(f"Поле «{label}»: введите корректную сумму, например 60 000. Расчёт остановлен до исправления.")
        st.stop()



# ==================================================
# СОХРАНЕНИЕ ОТЧЁТА: автономный HTML (таблицы и графики)
# ==================================================
REPORT_SECTIONS = []


def report_table(frame):
    """HTML-таблица с читаемыми значениями и выделением отрицательных сумм."""
    result = frame.copy()
    result = result.fillna("—")
    for column in result.columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            result[column] = result[column].map(lambda v: format_money(v) if pd.notna(v) else "—")
    html = result.to_html(index=False, border=0, escape=True)
    return html


def report_line_svg(series, title, y_label, height=290):
    """Встроенный SVG-график без зависимости от интернета и внешних файлов."""
    width, left, right, top, bottom = 920, 92, 28, 42, 58
    plot_width = width - left - right
    plot_height = height - top - bottom
    points = [v for _, values in series for v in values]
    if not points:
        return ""
    low, high = min(points), max(points)
    if low > 0:
        low = 0
    if high < 0:
        high = 0
    if high == low:
        high = low + 1
    padding = (high - low) * 0.07
    low -= padding
    high += padding
    count = max(len(values) for _, values in series)
    def x(i):
        return left + (i / max(1, count - 1)) * plot_width
    def y(v):
        return top + (high - v) / (high - low) * plot_height
    palette = ["#0875d1", "#e07a29", "#2a8a71"]
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
                f'<text x="{left}" y="24" font-size="17" font-weight="600">{escape(title)}</text>']
    for j in range(5):
        v = low + (high-low) * j / 4
        yy = y(v)
        elements.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#e4e9ef"/>')
        elements.append(f'<text x="{left-9}" y="{yy+4:.1f}" font-size="11" text-anchor="end" fill="#526070">{escape(format_money(v))}</text>')
    for i, (name, values) in enumerate(series):
        coords = " ".join(f"{x(j):.1f},{y(v):.1f}" for j, v in enumerate(values))
        color = palette[i % len(palette)]
        elements.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.6"/>')
        legend_x = left + i * 265
        elements.append(f'<line x1="{legend_x}" y1="{height-12}" x2="{legend_x+23}" y2="{height-12}" stroke="{color}" stroke-width="3"/>')
        elements.append(f'<text x="{legend_x+30}" y="{height-8}" font-size="12">{escape(name)}</text>')
    elements.append(f'<text x="{left}" y="{height-34}" font-size="11" fill="#526070">Периоды: 1–{count}; {escape(y_label)}</text>')
    elements.append('</svg>')
    return "".join(elements)


def report_stacked_svg(schedule, title, by_year=False):
    data = payment_structure(schedule, by_year)
    rows = data.reset_index()
    width, height, left, top, right, bottom = 920, 280, 80, 38, 20, 46
    plot_width, plot_height = width-left-right, height-top-bottom
    max_total = max(1.0, float(rows["Общая сумма погашения"].max()) * 1.08)
    n = len(rows)
    step = plot_width / max(1, n)
    bar_width = max(1, min(44, step * .74))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
             f'<text x="{left}" y="23" font-size="17" font-weight="600">{escape(title)}</text>']
    for idx, row in rows.iterrows():
        cx = left + (idx+.5)*step
        principal_height = float(row["Погашение кредита"])/max_total*plot_height
        interest_height = float(row["Проценты"])/max_total*plot_height
        bottom_y = top+plot_height
        parts.append(f'<rect x="{cx-bar_width/2:.1f}" y="{bottom_y-principal_height:.1f}" width="{bar_width:.1f}" height="{principal_height:.1f}" fill="#0875d1"/>')
        parts.append(f'<rect x="{cx-bar_width/2:.1f}" y="{bottom_y-principal_height-interest_height:.1f}" width="{bar_width:.1f}" height="{interest_height:.1f}" fill="#84caff"/>')
        if n <= 24 or idx % max(1, n//12) == 0:
            parts.append(f'<text x="{cx:.1f}" y="{bottom_y+16}" text-anchor="middle" font-size="10">{idx+1}</text>')
    parts.append(f'<text x="{left}" y="{height-6}" font-size="12">■ Основной долг (синий)　■ Проценты (голубой); {"годы" if by_year else "месяцы"}</text>')
    parts.append('</svg>')
    return ''.join(parts)


# Выбор расположен рядом с содержимым, а не в боковой панели.
# Пустой выбор означает: скачать всё. Выбор хотя бы одного пункта
# означает: скачать только отмеченные пункты.
REPORT_ITEMS = {}


def print_choice(section, item, label="", heading=None, level=3):
    """Компактный флажок рядом с заголовком; ничего не выбрано = весь отчёт."""
    key = f"print_select_{section}_{item}"
    REPORT_ITEMS.setdefault(str(section), []).append(item)
    if heading is not None:
        check_col, heading_col = st.columns([0.045, 0.955], vertical_alignment="center", gap="small")
        with check_col:
            st.checkbox(label or heading, value=False, key=key, label_visibility="collapsed")
        with heading_col:
            if level == 2:
                st.header(heading)
            elif level == 3:
                st.subheader(heading)
            else:
                st.markdown(f"**{heading}**")
    else:
        st.checkbox(label, value=False, key=key, label_visibility="collapsed")


def report_piece(item, html):
    return f'<!-- report-piece:{item}:start -->{html}<!-- report-piece:{item}:end -->'


def report_filter_content(number, content, selected_only=None):
    """Оставляет только выбранные блоки HTML внутри раздела.

    Если пользователь не отметил ни одного пункта во всём отчёте,
    раздел сохраняется целиком. Если отметил хотя бы один пункт,
    неотмеченные блоки исключаются, в том числе таблицы раздела 4.
    """
    if selected_only is None:
        selected_only = report_selection()
    if not selected_only or f"{number}:all" in selected_only:
        return content

    # Обрабатываем каждый блок независимо, чтобы выбор таблицы по годам
    # не мог автоматически включить помесячную таблицу.
    pattern = re.compile(
        r'<!-- report-piece:([a-zA-Z0-9_]+):start -->(.*?)<!-- report-piece:\1:end -->',
        re.S,
    )
    def keep(match):
        return match.group(2) if f"{number}:{match.group(1)}" in selected_only else ""
    return pattern.sub(keep, content)


def report_add(number, title, content):
    REPORT_SECTIONS.append((number, title, content))
    return content


def report_selection():
    return {f"{num}:{item}" for num, items in REPORT_ITEMS.items()
            for item in items if st.session_state.get(f"print_select_{num}_{item}", False)}


def report_selected_sections():
    chosen = report_selection()
    result = []
    for number, title, content in REPORT_SECTIONS:
        if chosen and not any(x.startswith(f"{number}:") for x in chosen):
            continue
        result.append((number, title, report_filter_content(number, content, chosen)))
    return result


def report_document(sections):
    stamp = datetime.now().strftime('%d.%m.%Y %H:%M')
    style = """<style>body{font:15px/1.55 Arial,sans-serif;color:#263343;max-width:1050px;margin:36px auto;padding:0 24px}
    h1{color:#17385d}h2{color:#17385d;border-bottom:2px solid #e0e9f4;padding-bottom:8px;margin-top:32px}
    h3{color:#264c72}table{border-collapse:collapse;width:100%;margin:14px 0 24px;font-size:13px}
    th,td{border:1px solid #d9e0e8;padding:9px;text-align:left}th{background:#eef3f8}
    td:not(:first-child){text-align:right}svg{display:block;max-width:100%;height:auto;margin:14px 0 24px}
    .note{color:#576879}.negative{color:#c72222;font-weight:bold}@media print{body{margin:12mm;max-width:none}section{break-inside:avoid}svg{break-inside:avoid}}</style>"""
    body = ''.join(f'<section><h2>{escape(number)}. {escape(title)}</h2>{content}</section>' for number,title,content in sections)
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Кредитный калькулятор — отчёт</title>'
            +style+'</head><body><h1>Дорого ли жить в кредит?</h1><p class="note">Отчёт сформирован: '
            +escape(stamp)+'</p>'+body+'</body></html>').encode('utf-8')


def save_section_button(number, title, html):
    st.download_button(
        f"📥 Сохранить раздел {number}",
        data=report_document([(str(number), title, report_filter_content(
            str(number), html,
            {f"{number}:{item}" for item in REPORT_ITEMS.get(str(number), [])
             if st.session_state.get(f"print_select_{number}_{item}", False)}
        ))]),
        file_name=f"kredit_razdel_{number}.html",
        mime="text/html",
        key=f"download_section_{number}",
        help="Автономный HTML-файл с расчётами, таблицами и графиками; открывается в браузере без интернета.",
    )


# ==================================================
# НАСТРОЙКИ СТРАНИЦЫ
# ==================================================

st.set_page_config(
    page_title="Дорого ли жить в кредит?",
    page_icon="💳",
    layout="wide"
)


st.title("💳 Дорого ли жить в кредит?")
st.subheader("Калькулятор для оценки стоимости кредита, долговой нагрузки и устойчивости семейного бюджета.")



# ==================================================
# ФУНКЦИИ РАСЧЁТА
# ==================================================

def annuity_credit(amount, annual_rate, months):
    rate = annual_rate / 100 / 12

    if rate == 0:
        payment = amount / months
    else:
        payment = (
            amount * rate * (1 + rate) ** months
            / ((1 + rate) ** months - 1)
        )

    balance = amount
    schedule = []

    for month in range(1, months + 1):
        interest = balance * rate
        principal = payment - interest

        if month == months:
            principal = balance
            actual_payment = principal + interest
        else:
            actual_payment = payment

        balance = max(0, balance - principal)

        schedule.append({
            "Месяц": month,
            "Платёж": actual_payment,
            "Проценты": interest,
            "Основной долг": principal,
            "Остаток долга": balance
        })

    return schedule


def differentiated_credit(amount, annual_rate, months):
    rate = annual_rate / 100 / 12
    principal = amount / months
    balance = amount

    schedule = []

    for month in range(1, months + 1):
        interest = balance * rate
        current_principal = (
            balance if month == months else principal
        )

        payment = current_principal + interest
        balance = max(0, balance - current_principal)

        schedule.append({
            "Месяц": month,
            "Платёж": payment,
            "Проценты": interest,
            "Основной долг": current_principal,
            "Остаток долга": balance
        })

    return schedule


def credit_totals(schedule, amount):
    total = sum(x["Платёж"] for x in schedule)

    return {
        "total": total,
        "overpayment": total - amount
    }




# ==================================================
# БОКОВАЯ ПАНЕЛЬ: ПАРАМЕТРЫ КРЕДИТА
# ==================================================

st.sidebar.header("Параметры кредита")

amount = money_input(
    "Сумма кредита", 500000.0, "amount_input",
    container=st.sidebar, min_value=1000.0
)

annual_rate = st.sidebar.number_input(
    "Годовая процентная ставка (%)",
    min_value=0.0,
    value=15.0,
    step=0.5
)

months = st.sidebar.number_input(
    "Срок кредита (месяцев)",
    min_value=1,
    max_value=600,
    value=12,
    step=1
)


# ==================================================
# РАСЧЁТ КРЕДИТА
# ==================================================



def year_group_band(total_months):
    """Отдельная нижняя строка оси X: одна подпись на каждый год."""
    years = pd.DataFrame([
        {"Начало": start - 0.5, "Конец": min(start + 11, total_months) + 0.5,
         "Середина": (start + min(start + 11, total_months)) / 2,
         "Подпись": f"{(start - 1) // 12 + 1} год"}
        for start in range(1, total_months + 1, 12)
    ])
    x_scale = alt.Scale(domain=[0.5, total_months + 0.5], nice=False)
    cells = alt.Chart(years).mark_rect(fill="#F3F5F9", stroke="#A9B3C2").encode(
        x=alt.X("Начало:Q", scale=x_scale, axis=None),
        x2="Конец:Q",
        y=alt.value(0), y2=alt.value(28),
    )
    labels = alt.Chart(years).mark_text(fontSize=13, color="#46546A", baseline="middle").encode(
        x=alt.X("Середина:Q", scale=x_scale, axis=None),
        y=alt.value(14), text="Подпись:N",
    )
    return alt.layer(cells, labels).properties(height=28)



def month_number_band(total_months):
    """Первая нижняя строка: номера месяцев 1, 2, ..., N."""
    rows = pd.DataFrame([
        {"Начало": month - 0.5, "Конец": month + 0.5,
         "Середина": month, "Номер": str(month)}
        for month in range(1, total_months + 1)
    ])
    x_scale = alt.Scale(domain=[0.5, total_months + 0.5], nice=False)
    cells = alt.Chart(rows).mark_rect(fill="#FFFFFF", stroke="#C9D1DB").encode(
        x=alt.X("Начало:Q", scale=x_scale, axis=None),
        x2="Конец:Q",
        y=alt.value(0), y2=alt.value(28),
    )
    labels = alt.Chart(rows).mark_text(fontSize=12, color="#46546A", baseline="middle").encode(
        x=alt.X("Середина:Q", scale=x_scale, axis=None),
        y=alt.value(14), text="Номер:N",
    )
    return alt.layer(cells, labels).properties(height=28)

print_choice(1, "all", heading="1. Сравнение вариантов погашения кредита", level=2)

annuity = annuity_credit(
    amount, annual_rate, int(months)
)

differentiated = differentiated_credit(
    amount, annual_rate, int(months)
)

annuity_result = credit_totals(annuity, amount)
diff_result = credit_totals(differentiated, amount)

# Процент переплаты: все начисленные проценты / сумма кредита × 100%.
annuity_overpayment_percent = annuity_result["overpayment"] / amount * 100
diff_overpayment_percent = diff_result["overpayment"] / amount * 100

first_annuity_payment = annuity[0]["Платёж"]
first_diff_payment = differentiated[0]["Платёж"]
first_payment_difference = first_diff_payment - first_annuity_payment
first_payment_difference_percent = (
    first_payment_difference / first_annuity_payment * 100
    if first_annuity_payment > 0 else 0.0
)
total_payment_difference = diff_result["total"] - annuity_result["total"]
total_payment_difference_percent = (
    total_payment_difference / annuity_result["total"] * 100
    if annuity_result["total"] > 0 else 0.0
)

# Сравнение показателей в единой таблице: строки всегда выровнены.
overpayment_difference = diff_result["overpayment"] - annuity_result["overpayment"]
overpayment_difference_percent = (
    overpayment_difference / annuity_result["overpayment"] * 100
    if annuity_result["overpayment"] > 0 else 0.0
)
comparison_table = pd.DataFrame({
    "Показатель": [
        "Первый платёж, ₽",
        "Общая сумма выплат, ₽",
        "Переплата, ₽",
        "Переплата по кредиту, %",
    ],
    "Аннуитетный кредит": [
        format_money(first_annuity_payment),
        format_money(annuity_result["total"]),
        format_money(annuity_result["overpayment"]),
        f"{annuity_overpayment_percent:.2f}%",
    ],
    "Дифференцированный кредит": [
        format_money(first_diff_payment),
        format_money(diff_result["total"]),
        format_money(diff_result["overpayment"]),
        f"{diff_overpayment_percent:.2f}%",
    ],
    "Разница, ₽": [
        format_money(first_payment_difference),
        format_money(total_payment_difference),
        format_money(overpayment_difference),
        "—",
    ],
    "Разница, %": [
        f"{first_payment_difference_percent:+.2f}%",
        f"{total_payment_difference_percent:+.2f}%",
        f"{overpayment_difference_percent:+.2f}%",
        f"{diff_overpayment_percent - annuity_overpayment_percent:+.2f} п.п.",
    ],
})
# Чуть более крупный шрифт для таблицы сравнения.
st.markdown(
    """
    <style>
    .credit-comparison-table {width:100%; border-collapse:collapse; font-size:17px;}
    .credit-comparison-table th, .credit-comparison-table td {
        border:1px solid #d9dfe5; padding:11px 12px; vertical-align:middle;
    }
    .credit-comparison-table th {background:#f4f5f7; font-weight:600; text-align:left;}
    .credit-comparison-table td:not(:first-child) {text-align:right; white-space:nowrap;}
    .credit-comparison-wrap {overflow-x:auto; margin-bottom:12px;}
    </style>
    """,
    unsafe_allow_html=True,
)
print_choice(1, "comparison", heading="Сравнение вариантов", level=3)
st.markdown(
    '<div class="credit-comparison-wrap">'
    + comparison_table.to_html(index=False, classes="credit-comparison-table", border=0)
    + '</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Разница = дифференцированный кредит − аннуитетный кредит. "
    "Разница в процентах рассчитана относительно аннуитетной схемы; "
    "для строки «Переплата по кредиту, %» показана разница в процентных пунктах (п.п.)."
)

st.subheader("Основной долг и проценты в составе платежей")
print_choice(1, "structure_charts", heading="График платежей", level=4)
st.caption(
    "Каждый столбец состоит из погашения основного долга и процентов. "
    "Высота столбца — общая сумма платежа за месяц или год."
)

def payment_structure(schedule, by_year):
    rows = pd.DataFrame({
        "Месяц": [item["Месяц"] for item in schedule],
        "Погашение кредита": [item["Основной долг"] for item in schedule],
        "Проценты": [item["Проценты"] for item in schedule],
    })
    if by_year:
        rows["Год"] = (rows["Месяц"] - 1) // 12 + 1
        result = rows.groupby("Год")[["Погашение кредита", "Проценты"]].sum()
    else:
        result = rows.set_index("Месяц")[["Погашение кредита", "Проценты"]]
    result["Общая сумма погашения"] = result["Погашение кредита"] + result["Проценты"]
    return result


by_year = months > 24
st.caption("Разбивка по годам" if by_year else "Разбивка по месяцам")
print_choice(1, "schedule_tables", heading="Таблицы погашения", level=4)
chart_col1, chart_col2 = st.columns(2)

annuity_structure = payment_structure(annuity, by_year)
diff_structure = payment_structure(differentiated, by_year)

# Общий масштаб Y и одинаковая высота области построения выравнивают оси X.
max_payment = max(
    (annuity_structure["Погашение кредита"] + annuity_structure["Проценты"]).max(),
    (diff_structure["Погашение кредита"] + diff_structure["Проценты"]).max(),
)
common_y_max = float(max_payment) * 1.08 if max_payment > 0 else 1.0


def payment_chart(structure):
    axis_name = "Год" if by_year else "Месяц"
    chart_data = structure.reset_index().melt(
        id_vars=[axis_name],
        value_vars=["Погашение кредита", "Проценты"],
        var_name="Состав платежа",
        value_name="Сумма, ₽",
    )
    chart_data[axis_name] = chart_data[axis_name].astype(str)
    axis_order = [str(i) for i in structure.index]
    return (
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            x=alt.X(f"{axis_name}:N", sort=axis_order, title=axis_name),
            y=alt.Y(
                "Сумма, ₽:Q",
                stack="zero",
                scale=alt.Scale(domain=[0, common_y_max]),
                title=None,
            ),
            color=alt.Color(
                "Состав платежа:N",
                scale=alt.Scale(
                    domain=["Погашение кредита", "Проценты"],
                    range=["#0875d1", "#84caff"],
                ),
                title=None,
            ),
            tooltip=[axis_name, "Состав платежа", alt.Tooltip("Сумма, ₽:Q", format=",.0f")],
        )
        .properties(height=340)
    )


with chart_col1:
    st.markdown("**Аннуитетная схема**")
    st.altair_chart(payment_chart(annuity_structure), use_container_width=True)
    st.dataframe(
        annuity_structure.style.format(format_money),
        width="stretch",
    )

with chart_col2:
    st.markdown("**Дифференцированная схема**")
    st.altair_chart(payment_chart(diff_structure), use_container_width=True)
    st.dataframe(
        diff_structure.style.format(format_money),
        width="stretch",
    )


print_choice(1, "payment_chart", heading=("Ежегодный платёж по кредиту" if by_year else "Ежемесячный платёж по кредиту"), level=3)
st.caption(
    "Линии показывают общую сумму платежей (основной долг и проценты) "
    + ("за каждый год" if by_year else "за каждый месяц")
    + " для аннуитетной и дифференцированной схем погашения."
)

payment_rows = []
for name, schedule in (("Аннуитетная", annuity), ("Дифференцированная", differentiated)):
    for item in schedule:
        payment_rows.append({
            "Месяц": item["Месяц"],
            "Схема": name,
            "Платёж, ₽": item["Платёж"],
        })

payment_data = pd.DataFrame(payment_rows)
axis_name = "Год" if by_year else "Месяц"
if by_year:
    payment_data["Год"] = (payment_data["Месяц"] - 1) // 12 + 1
    payment_data = (
        payment_data.groupby(["Схема", "Год"], as_index=False)["Платёж, ₽"].sum()
    )
else:
    payment_data = payment_data.rename(columns={"Месяц": axis_name})

line_chart = (
    alt.Chart(payment_data)
    .mark_line(strokeWidth=3, point=True)
    .encode(
        x=alt.X(f"{axis_name}:Q", title="Год кредитования" if by_year else None, scale=alt.Scale(domain=[0.5, int(months) + 0.5], nice=False) if not by_year else alt.Undefined, axis=alt.Axis(values=list(range(1, (int(months) - 1) // 12 + 2)), format="d") if by_year else None),
        y=alt.Y("Платёж, ₽:Q", title="Сумма платежа, ₽", scale=alt.Scale(zero=True)),
        color=alt.Color(
            "Схема:N", title="Способ погашения",
            scale=alt.Scale(
                domain=["Аннуитетная", "Дифференцированная"],
                range=["#0875d1", "#e07a29"],
            ),
        ),
        tooltip=["Схема:N", f"{axis_name}:Q", alt.Tooltip("Платёж, ₽:Q", format=",.0f")],
    )
    .properties(height=360)
)
if not by_year:
    line_chart = alt.vconcat(
        line_chart, month_number_band(int(months)), year_group_band(int(months)), spacing=0
    ).resolve_scale(x="shared")
st.altair_chart(line_chart, use_container_width=True)


section_1 = (
    report_piece('comparison', f'<p><b>Сумма кредита:</b> {format_money(amount)} ₽; <b>ставка:</b> {annual_rate:.2f}% годовых; <b>срок:</b> {int(months)} мес.</p>'
        + report_table(comparison_table)
        + '<p class="note">Разница = дифференцированный − аннуитетный; для процентной переплаты — п.п.</p>')
    + report_piece('structure_charts', report_stacked_svg(annuity, 'Структура аннуитетных платежей', by_year)
        + report_stacked_svg(differentiated, 'Структура дифференцированных платежей', by_year))
    + report_piece('payment_chart', report_line_svg([
        ('Аннуитетная', [float(x['Платёж']) for x in annuity]),
        ('Дифференцированная', [float(x['Платёж']) for x in differentiated]),
    ], 'Ежемесячные платежи по кредиту', 'руб.'))
    + report_piece('schedule_tables', '<h3>График погашения: аннуитет</h3>' + report_table(pd.DataFrame(annuity))
        + '<h3>График погашения: дифференцированный</h3>' + report_table(pd.DataFrame(differentiated)))
)
save_section_button(1, 'Сравнение вариантов погашения кредита', report_add('1', 'Сравнение вариантов погашения кредита', section_1))

# ==================================================
# ДОХОДЫ СЕМЬИ
# ==================================================

print_choice(2, "all", heading="2. Доходы и расходы семьи", level=2)
print_choice(2, "budget", heading="Таблица семейного бюджета", level=4)

# Исходные данные о семье вводятся в боковой панели.
st.sidebar.header("Доходы семьи")
borrower_income = money_input(
    "Ежемесячный доход заёмщика", 70000.0, "borrower_income_input",
    container=st.sidebar
)

co_count = st.sidebar.number_input(
    "Количество созаёмщиков (работающих членов семьи)",
    min_value=0,
    max_value=10,
    value=1,
    step=1
)

co_incomes = []
for i in range(int(co_count)):
    income = money_input(
        f"Ежемесячный доход созаёмщика №{i + 1}",
        30000.0, f"co_income_{i}", container=st.sidebar
    )
    co_incomes.append(income)

total_income = borrower_income + sum(co_incomes)

st.sidebar.subheader("Расходы семьи")
actual_expenses = money_input(
    "Ежемесячные расходы семьи (без кредитов)", 45000.0,
    "actual_expenses_input", container=st.sidebar
)
other_credits = money_input(
    "Ежемесячные платежи по другим кредитам", 5000.0,
    "other_credits_input", container=st.sidebar
)
family_count = st.sidebar.number_input(
    "Общее количество членов семьи",
    min_value=1,
    max_value=30,
    value=3,
    step=1
)
living_minimum = money_input(
    "Прожиточный минимум в регионе на человека", 20000.0,
    "living_minimum_input", container=st.sidebar
)

# На основной странице остаются результаты и выбор способа оценки расходов.
st.metric("Общий доход семьи", format_money(total_income))

conditional_expenses = living_minimum * family_count

st.markdown("**Общие расходы семьи с учётом действующих кредитов**")

expense_choice = st.radio(
    "Выбери расходы для расчёта финансовой устойчивости",
    ["Фактические расходы семьи", "Расходы по прожиточному минимуму"],
    format_func=lambda choice: (
        f"Расходы по прожиточному минимуму — {format_money(conditional_expenses + other_credits)} ₽"
        if choice == "Расходы по прожиточному минимуму"
        else f"Фактические расходы семьи — {format_money(actual_expenses + other_credits)} ₽"
    ),
    horizontal=True,
    index=None,  # Без выбора используем фактические расходы пользователя.
    key="expense_choice"
)

if expense_choice == "Расходы по прожиточному минимуму":
    expenses = conditional_expenses
    effective_expense_choice = "Расходы по прожиточному минимуму"
else:
    # В том числе когда пользователь не выбрал ни один вариант.
    expenses = actual_expenses
    effective_expense_choice = "Фактические расходы семьи"

# Платежи по действующим кредитам учитываются один раз.
household_expenses_with_existing_credits = expenses + other_credits

free_cash_balance = total_income - household_expenses_with_existing_credits
st.markdown(
    f"**Остаток свободных денежных средств: {format_money(free_cash_balance)} ₽**"
)
free_cash_percent = (free_cash_balance / total_income * 100) if total_income > 0 else None
st.markdown(
    "**Остаток свободных денежных средств в процентах от дохода: "
    + (f"{free_cash_percent:.2f}%" if free_cash_percent is not None else "не рассчитывается (доход равен нулю)")
    + "**"
)
st.caption(
    "Разница между доходами семьи и выбранными расходами "
    "с учётом действующих кредитов (без нового кредита)."
)



section_2 = report_piece("budget", (
    '<p>Сведения о семейном бюджете (до нового кредита).</p>'
    + report_table(pd.DataFrame([
        ('Доход заёмщика, ₽', borrower_income),
        *[(f'Доход созаёмщика №{i+1}, ₽', v) for i,v in enumerate(co_incomes)],
        ('Общий доход семьи, ₽', total_income),
        ('Фактические расходы без кредитов, ₽', actual_expenses),
        ('Платежи по действующим кредитам, ₽', other_credits),
        ('Членов семьи', family_count),
        ('Прожиточный минимум на человека, ₽', living_minimum),
        ('Расходы по прожиточному минимуму, ₽', conditional_expenses),
        ('Выбранные расходы без кредитов, ₽', expenses),
        ('Расходы с действующими кредитами, ₽', household_expenses_with_existing_credits),
        ('Свободные средства до нового кредита, ₽', free_cash_balance),
    ], columns=['Показатель', 'Значение']))
    + f'<p>Выбранный вариант расходов: <b>{escape(effective_expense_choice)}</b>.</p>'
))
save_section_button(2, 'Доходы и расходы семьи', report_add('2', 'Доходы и расходы семьи', section_2))

# ==================================================
# ВЫБОР СХЕМЫ
# ==================================================

print_choice(3, "all", heading="3. Кредитная нагрузка на семейный бюджет в первый месяц", level=2)
print_choice(3, "load", heading="Таблица долговой и финансовой нагрузки", level=4)
st.caption(
    "Долговая нагрузка = (платежи по действующим кредитам + "
    "первый платёж по новому кредиту) / доходы семьи × 100%. "
    "Расходы на жизнь в эту формулу не входят."
)

credit_schemes = {
    "Аннуитетная": annuity,
    "Дифференцированная": differentiated,
}
col_annuity, col_differentiated = st.columns(2)
for col, (name, schedule) in zip(
    (col_annuity, col_differentiated), credit_schemes.items()
):
    new_payment = schedule[0]["Платёж"]
    combined_credit_payments = other_credits + new_payment
    debt_ratio = (
        combined_credit_payments / total_income * 100
        if total_income > 0 else None
    )
    with col:
        st.subheader(f"{name} схема")
        st.metric("Первый платёж по новому кредиту", f"{format_money(new_payment)} ₽")
        st.metric("Платежи по всем кредитам", f"{format_money(combined_credit_payments)} ₽")
        st.metric(
            "Долговая нагрузка",
            f"{debt_ratio:.2f}%" if debt_ratio is not None else "Не рассчитывается"
        )
        financial_ratio = (
            (household_expenses_with_existing_credits + new_payment)
            / total_income * 100
            if total_income > 0 else None
        )
        st.metric(
            "Финансовая нагрузка",
            f"{financial_ratio:.2f}%" if financial_ratio is not None else "Не рассчитывается"
        )
        # Свободные средства после всех расходов и нового кредита.
        remaining_cash = total_income - household_expenses_with_existing_credits - new_payment
        remaining_percent = (
            remaining_cash / total_income * 100 if total_income > 0 else None
        )
        st.metric(
            "Остаток свободных денежных средств",
            f"{format_money(remaining_cash)} ₽"
        )
        st.metric(
            "Остаток свободных денежных средств в процентах от дохода",
            f"{remaining_percent:.2f}%" if remaining_percent is not None else "Не рассчитывается"
        )
st.caption(
    "Финансовая нагрузка = (выбранные расходы семьи с учётом действующих кредитов "
    "+ первый платёж по новому кредиту) / доходы семьи × 100%."
)
if total_income <= 0:
    st.warning("Доходы семьи равны нулю: нагрузку в процентах рассчитать нельзя.")

section_3_rows = []
for name, schedule in credit_schemes.items():
    payment = schedule[0]['Платёж']
    credits = other_credits + payment
    total_spending = household_expenses_with_existing_credits + payment
    section_3_rows.append({
        'Схема': name,
        'Первый платёж, ₽': payment,
        'Все кредитные платежи, ₽': credits,
        'Долговая нагрузка, %': f'{credits / total_income * 100:.2f}%' if total_income > 0 else '—',
        'Финансовая нагрузка, %': f'{total_spending / total_income * 100:.2f}%' if total_income > 0 else '—',
        'Остаток свободных средств, ₽': total_income - total_spending,
    })
section_3 = report_piece("load", (
    '<p>Показатели за первый месяц. Финансовая нагрузка рассчитана по выбранным расходам семьи.</p>'
    + report_table(pd.DataFrame(section_3_rows))
))
save_section_button(3, 'Кредитная нагрузка на семейный бюджет в первый месяц', report_add('3', 'Кредитная нагрузка на семейный бюджет в первый месяц', section_3))

# ==================================================
# ИНФЛЯЦИОННЫЕ ОЖИДАНИЯ
# ==================================================

print_choice(4, "all", heading="4. Оценка кредитной нагрузки с учётом инфляционных ожиданий", level=2)
st.caption("В этом разделе используются только фактические расходы семьи (без кредитов). Расходы по прожиточному минимуму не участвуют в расчётах и не индексируются.")
st.write(
    "Укажите отдельно годовой темп роста доходов семьи и инфляцию фактических расходов семьи. "
    "Отрицательный процент означает снижение доходов или расходов (дефляцию). "
    "График начинается с первого платежа по кредиту. В течение первых 12 месяцев "
    "доходы и расходы не меняются. Начиная с 13-го месяца, в начале каждого "
    "следующего года оба показателя индексируются независимо. "
    "Платежи по действующим кредитам не индексируются, "
    "а платежи по новому кредиту берутся из графика погашения."
)

income_growth_percent = st.number_input(
    "Годовой темп роста доходов, %",
    min_value=-99.9,
    value=0.0,
    step=1.0,
    format="%.1f",
    key="income_growth_percent",
)
expense_inflation_percent = st.number_input(
    "Годовая инфляция фактических расходов семьи (без кредитов), %",
    min_value=-99.9,
    value=0.0,
    step=1.0,
    format="%.1f",
    key="expense_inflation_percent",
)
st.caption(
    "Каждый процент задаётся независимо. В первый год используются исходные суммы; "
    "с 13-го, 25-го, 37-го месяцев и далее доходы и фактические расходы без кредитов "
    "изменяются каждый год на свой установленный процент (отрицательное значение означает снижение)."
)

# Для каждого месяца используется фактический платёж из графика кредита.
# Годовой рост начинается с 13-го месяца, затем с 25-го, 37-го и т. д.
inflation_rows = []
for scheme_name, schedule in credit_schemes.items():
    for entry in schedule:
        month = entry["Месяц"]
        # Месяцы 1–12: исходные доходы и расходы. Начиная с месяца 13
        # ежегодный рост применяется к первому платежу каждого нового года.
        completed_years = max(0, (month - 1) // 12)
        income_growth_factor = (1 + income_growth_percent / 100) ** completed_years
        expense_growth_factor = (1 + expense_inflation_percent / 100) ** completed_years
        monthly_income = total_income * income_growth_factor
        monthly_living_expenses = actual_expenses * expense_growth_factor

        current_credit_payment = entry["Платёж"]
        total_credit_payments = other_credits + current_credit_payment
        all_expenses = monthly_living_expenses + total_credit_payments
        remaining = monthly_income - all_expenses
        inflation_rows.append({
            "Месяц": month,
            "Способ погашения": scheme_name,
            "Доходы, ₽": monthly_income,
            "Расходы без кредитов, ₽": monthly_living_expenses,
            "Все кредитные платежи, ₽": total_credit_payments,
            "Остаток свободных денежных средств, ₽": remaining,
            "Долговая нагрузка, %": (
                total_credit_payments / monthly_income * 100
                if monthly_income > 0 else None
            ),
            "Финансовая нагрузка, %": (
                all_expenses / monthly_income * 100
                if monthly_income > 0 else None
            ),
        })

inflation_df = pd.DataFrame(inflation_rows)
print_choice(4, "balance_chart", heading="Ежемесячный остаток свободных денежных средств", level=3)
monthly_balance_chart = (
    alt.Chart(inflation_df)
    .mark_line(strokeWidth=2.5)
    .encode(
        x=alt.X(
            "Месяц:Q", title="Месяц кредита" if months <= 24 else "Год кредитования",
            scale=alt.Scale(domain=[0.5, int(months) + 0.5], nice=False),
            axis=(
                None
                if months <= 24 else
                alt.Axis(
                    values=list(range(1, int(months) + 1, 12)),
                    labelExpr="floor((datum.value - 1) / 12) + 1",
                    title="Год кредитования", grid=True,
                )
            ),
        ),
        y=alt.Y(
            "Остаток свободных денежных средств, ₽:Q",
            title="Остаток свободных денежных средств, ₽",
            scale=alt.Scale(zero=False),
        ),
        color=alt.Color("Способ погашения:N", title="Способ погашения"),
        tooltip=[
            alt.Tooltip("Месяц:Q", format=".0f"),
            "Способ погашения:N",
            alt.Tooltip("Доходы, ₽:Q", format=",.0f"),
            alt.Tooltip("Расходы без кредитов, ₽:Q", format=",.0f"),
            alt.Tooltip("Все кредитные платежи, ₽:Q", format=",.0f"),
            alt.Tooltip("Остаток свободных денежных средств, ₽:Q", format=",.0f"),
        ],
    )
    .properties(height=380)
)
# Отдельная строка с группировкой месяцев по годам, без повторения года
# над каждым месяцем. Для длинных кредитов показывается только год.
if months <= 24:
    monthly_balance_chart = alt.vconcat(
        monthly_balance_chart, month_number_band(int(months)), year_group_band(int(months)), spacing=0
    ).resolve_scale(x="shared")
st.altair_chart(monthly_balance_chart, use_container_width=True)
st.caption(
    "Каждая линия показывает остаток после расходов на жизнь, действующих кредитов "
    "и фактического платежа по новому кредиту за соответствующий месяц. "
    "График начинается с первого платежа без изменения доходов и расходов. "
    "Доходы и фактические расходы индексируются независимо с первого платежа каждого последующего года "
    "(13-й, 25-й, 37-й месяцы и далее); "
    "если срок кредита не превышает 12 месяцев, изменения не наступают."
)

# Отдельные горизонтальные таблицы по каждой схеме погашения.
# Столбцы — первые месяцы каждого года: 1, 13, 25, 37 и т. д.
annual_reference_months = list(range(1, int(months) + 1, 12))
annual_indicators = inflation_df[
    inflation_df["Месяц"].isin(annual_reference_months)
].copy()

st.subheader("Показатели в первый месяц каждого года кредита")
print_choice(4, "year_table", heading="Таблица по годам", level=4)
print_choice(4, "month_table", heading="Помесячная таблица", level=4)
st.caption(
    "Столбцы соответствуют 1-му, 13-му, 25-му, 37-му месяцам и далее "
    "в пределах срока кредита. Индексация доходов и расходов начинается с 13-го месяца."
)

indicator_labels = [
    "Долговая нагрузка, %",
    "Финансовая нагрузка, %",
    "Остаток свободных денежных средств, ₽",
]

for scheme_name in credit_schemes:
    st.markdown(f"**{scheme_name} схема**")
    scheme_indicators = annual_indicators[
        annual_indicators["Способ погашения"] == scheme_name
    ].set_index("Месяц")

    # Значения форматируются после расчётов, чтобы не терять точность.
    indicator_table = pd.DataFrame(index=indicator_labels)
    for month in annual_reference_months:
        if month not in scheme_indicators.index:
            continue
        row = scheme_indicators.loc[month]
        indicator_table[f"{month}-й месяц"] = [
            f"{row['Долговая нагрузка, %']:.2f}%"
            if pd.notna(row["Долговая нагрузка, %"]) else "—",
            f"{row['Финансовая нагрузка, %']:.2f}%"
            if pd.notna(row["Финансовая нагрузка, %"]) else "—",
            f"{format_money(row['Остаток свободных денежных средств, ₽'])} ₽",
        ]
    indicator_table.index.name = "Показатели"
    # Отрицательные значения выделяются красным, включая проценты и рубли.
    def negative_red(value):
        return "color: #d62828; font-weight: 600" if str(value).strip().startswith(("-", "−")) else ""

    st.dataframe(
        indicator_table.reset_index().style.map(negative_red),
        hide_index=True,
        use_container_width=True,
    )

section_4 = (
    report_piece('balance_chart', f'<p>Годовой рост доходов: {income_growth_percent:.1f}%; изменение расходов: {expense_inflation_percent:.1f}%.</p>'
        + report_line_svg([
            (name, inflation_df[inflation_df['Способ погашения'] == name]['Остаток свободных денежных средств, ₽'].tolist())
            for name in credit_schemes
        ], 'Остаток свободных денежных средств по месяцам', 'руб.'))
    + report_piece('year_table', '<h3>Показатели на начало каждого года</h3>' + report_table(annual_indicators))
    + report_piece('month_table', '<h3>Помесячные показатели</h3>' + report_table(inflation_df))
)
save_section_button(4, 'Оценка кредитной нагрузки с учётом инфляционных ожиданий', report_add('4', 'Оценка кредитной нагрузки с учётом инфляционных ожиданий', section_4))

# ==================================================
# РЕАЛЬНАЯ СТОИМОСТЬ КРЕДИТА: НЕЗАВИСИМАЯ СТАВКА ДИСКОНТИРОВАНИЯ
# ==================================================
print_choice(5, "all", heading="5. Реальная стоимость кредита с учётом инфляции потребительских цен", level=2)
st.write(
    "Ставка дисконтирования отражает предполагаемую инфляцию потребительских цен и задаётся отдельно от изменения расходов семьи "
    "или темпа роста доходов семьи. Она показывает, как будущие платежи "
    "оцениваются в рублях на начало кредитования."
)
discount_rate_percent = st.number_input(
    "Годовая ставка дисконтирования (инфляция), %",
    min_value=-99.9,
    value=0.0,
    step=1.0,
    format="%.1f",
    key="discount_rate_percent",
    help="Предполагаемая инфляция потребительских цен для приведения будущих платежей к стоимости денег на начало кредита. "
         "Может отличаться от инфляции расходов и процентной ставки по кредиту.",
)
st.caption(
    "Платёж первого месяца принимается без дисконтирования. Для месяца k "
    "используется коэффициент (1 + d/100)^((k − 1)/12), где d — заданная годовая ставка. "
    "Отрицательная ставка означает увеличение приведённой стоимости будущих платежей."
)

real_payment_rows = []
real_payment_series = {}
nominal_totals = {}
real_totals = {}
for scheme_name, schedule in credit_schemes.items():
    real_values = []
    nominal_values = []
    for payment in schedule:
        month_number = int(payment["Месяц"])
        nominal = float(payment["Платёж"])
        discount_factor = (1.0 + discount_rate_percent / 100.0) ** ((month_number - 1) / 12.0)
        real_value = nominal / discount_factor
        nominal_values.append(nominal)
        real_values.append(real_value)
        real_payment_rows.append({
            "Месяц": month_number,
            "Схема": scheme_name,
            "Номинальный платёж, ₽": nominal,
            "Приведённый платёж, ₽": real_value,
        })
    real_payment_series[scheme_name] = real_values
    nominal_totals[scheme_name] = sum(nominal_values)
    real_totals[scheme_name] = sum(real_values)

annuity_real_total = real_totals["Аннуитетная"]
diff_real_total = real_totals["Дифференцированная"]
real_difference = diff_real_total - annuity_real_total
real_difference_percent = real_difference / annuity_real_total * 100 if annuity_real_total else 0.0

# Приведённая переплата — аналитическая разность между суммой
# дисконтированных платежей и первоначальной суммой кредита.
# Она не равна фактическим процентам, уплачиваемым банку.
nominal_overpayments = {name: nominal_totals[name] - amount for name in credit_schemes}
real_overpayments = {name: real_totals[name] - amount for name in credit_schemes}


def comparison_money_row(label, annuity_value, diff_value):
    difference = diff_value - annuity_value
    percent = difference / annuity_value * 100 if abs(annuity_value) > 1e-10 else None
    return {
        "Показатель": label,
        "Аннуитетный кредит": format_money(annuity_value),
        "Дифференцированный кредит": format_money(diff_value),
        "Разница, ₽": format_money(difference),
        "Разница, %": f"{percent:+.2f}%" if percent is not None else "—",
    }


def comparison_percent_row(label, annuity_value, diff_value):
    return {
        "Показатель": label,
        "Аннуитетный кредит": f"{annuity_value:.2f}%",
        "Дифференцированный кредит": f"{diff_value:.2f}%",
        "Разница, ₽": "—",
        "Разница, %": f"{diff_value - annuity_value:+.2f} п.п.",
    }


real_comparison = pd.DataFrame([
    comparison_money_row("Номинальная сумма выплат, ₽", nominal_totals["Аннуитетная"], nominal_totals["Дифференцированная"]),
    comparison_money_row("Номинальная переплата, ₽", nominal_overpayments["Аннуитетная"], nominal_overpayments["Дифференцированная"]),
    comparison_percent_row("Номинальная переплата, %", nominal_overpayments["Аннуитетная"] / amount * 100, nominal_overpayments["Дифференцированная"] / amount * 100),
    comparison_money_row("Приведённая сумма выплат, ₽", annuity_real_total, diff_real_total),
    comparison_money_row("Приведённая переплата, ₽", real_overpayments["Аннуитетная"], real_overpayments["Дифференцированная"]),
    comparison_percent_row("Приведённая переплата, %", real_overpayments["Аннуитетная"] / amount * 100, real_overpayments["Дифференцированная"] / amount * 100),
])

print_choice(5, "comparison", heading="Сравнение номинальной и приведённой стоимости", level=3)
st.markdown(
    '<div class="credit-comparison-wrap">'
    + real_comparison.to_html(index=False, classes="credit-comparison-table", border=0)
    + '</div>',
    unsafe_allow_html=True,
)
st.write(
    f"Разница приведённых сумм (дифференцированный минус аннуитетный): "
    f"**{format_money(real_difference)} ₽ ({real_difference_percent:+.2f}%)**. "
    "Отрицательное значение означает меньшую приведённую стоимость дифференцированного кредита."
)
st.caption(
    "Процентная разница для денежных показателей рассчитана относительно аннуитетной схемы; "
    "для процентных показателей разница указана в процентных пунктах (п.п.). "
    "Приведённая переплата = приведённая сумма выплат − первоначальная сумма кредита. "
    "Она может быть отрицательной и не является фактическими процентами, уплаченными банку."
)

print_choice(5, "real_chart", heading="График приведённых платежей", level=3)
real_payment_df = pd.DataFrame(real_payment_rows)
real_chart = (
    alt.Chart(real_payment_df)
    .mark_line(strokeWidth=2.7)
    .encode(
        x=alt.X("Месяц:Q", title="Месяц кредитования", axis=alt.Axis(format="d")),
        y=alt.Y("Приведённый платёж, ₽:Q", title="В рублях на начало кредита"),
        color=alt.Color("Схема:N", title="Способ погашения",
            scale=alt.Scale(domain=["Аннуитетная", "Дифференцированная"],
                            range=["#0875d1", "#e07a29"])),
        tooltip=["Схема:N", "Месяц:Q", alt.Tooltip("Приведённый платёж, ₽:Q", format=",.2f")],
    )
    .properties(height=350)
)
st.altair_chart(real_chart, use_container_width=True)

print_choice(5, "real_table", heading="Помесячная таблица приведённых платежей", level=3)
st.dataframe(
    real_payment_df.style.format({
        "Номинальный платёж, ₽": lambda x: format_money(x),
        "Приведённый платёж, ₽": lambda x: format_money(x),
    }),
    use_container_width=True,
    hide_index=True,
)
st.caption(
    "Приведённая стоимость — аналитический показатель, а не фактическая сумма "
    "платежей банку. При нулевой ставке дисконтирования она равна номинальной сумме выплат."
)

section_5 = (
    report_piece("comparison",
        f'<p><b>Годовая ставка дисконтирования:</b> {discount_rate_percent:.1f}%. '
        'Она задаётся отдельно от темпа роста расходов семьи.</p>'
        + report_table(real_comparison)
        + f'<p>Разница приведённых сумм: {format_money(real_difference)} ₽ '
          f'({real_difference_percent:+.2f}%).</p>'
        + '<p>Приведённая переплата = приведённая сумма выплат − сумма кредита; это не фактические проценты банку. Разница процентных показателей указана в п.п.</p>')
    + report_piece("real_chart", report_line_svg([
        ("Аннуитетная", real_payment_series["Аннуитетная"]),
        ("Дифференцированная", real_payment_series["Дифференцированная"]),
    ], "Приведённые ежемесячные платежи", "рубли на начало кредита"))
    + report_piece("real_table", '<h3>Помесячная таблица приведённых платежей</h3>'
                   + report_table(real_payment_df))
)
save_section_button(5, 'Реальная стоимость кредита с учётом инфляции потребительских цен',
                    report_add('5', 'Реальная стоимость кредита с учётом инфляции потребительских цен', section_5))

# ==================================================
# ИТОГИ РАСЧЁТА
# ==================================================
print_choice(6, "all", heading="6. Итоги расчёта", level=2)

st.subheader("Переплата по кредиту")
summary_col_annuity, summary_col_diff = st.columns(2)
with summary_col_annuity:
    st.markdown("**Аннуитетный кредит**")
    st.write(f"Переплата: **{format_money(annuity_result['overpayment'])} ₽**")
    st.write(f"Переплата от суммы кредита: **{annuity_overpayment_percent:.2f}%**")
with summary_col_diff:
    st.markdown("**Дифференцированный кредит**")
    st.write(f"Переплата: **{format_money(diff_result['overpayment'])} ₽**")
    st.write(f"Переплата от суммы кредита: **{diff_overpayment_percent:.2f}%**")


st.subheader("Переплата по кредиту с учётом инфляции")
real_summary_ann, real_summary_diff = st.columns(2)
with real_summary_ann:
    st.markdown("**Аннуитетный кредит**")
    st.write(f"Приведённая переплата: **{format_money(real_overpayments['Аннуитетная'])} ₽**")
    st.write(f"От суммы кредита: **{real_overpayments['Аннуитетная'] / amount * 100:.2f}%**")
with real_summary_diff:
    st.markdown("**Дифференцированный кредит**")
    st.write(f"Приведённая переплата: **{format_money(real_overpayments['Дифференцированная'])} ₽**")
    st.write(f"От суммы кредита: **{real_overpayments['Дифференцированная'] / amount * 100:.2f}%**")
st.caption("Приведённая переплата — сумма дисконтированных платежей за вычетом суммы кредита; она не равна процентам, фактически выплаченным банку.")


def credit_month_description(month_number):
    """Номер месяца кредита и месяц соответствующего года кредитования."""
    year_number = (month_number - 1) // 12 + 1
    month_in_year = (month_number - 1) % 12 + 1
    return f"{month_number}-й месяц кредита ({month_in_year}-й месяц {year_number}-го года)"


st.subheader("Когда дифференцированный платёж становится меньше аннуитетного")
first_lower_diff_month = next(
    (
        i + 1
        for i, (ann_item, diff_item) in enumerate(zip(annuity, differentiated))
        if diff_item["Платёж"] < ann_item["Платёж"] - 1e-8
    ),
    None,
)
if first_lower_diff_month is not None:
    st.write(
        "Впервые дифференцированный платёж становится меньше аннуитетного "
        f"в **{credit_month_description(first_lower_diff_month)}**."
    )
else:
    st.write(
        "За весь срок кредита дифференцированный платёж "
        "не становится меньше аннуитетного."
    )

st.subheader("Когда проценты становятся меньше погашаемого основного долга")
for scheme_name, schedule in credit_schemes.items():
    first_principal_dominant_month = next(
        (
            int(item["Месяц"])
            for item in schedule
            if item["Проценты"] < item["Основной долг"] - 1e-8
        ),
        None,
    )
    if first_principal_dominant_month is not None:
        st.write(
            f"**{scheme_name} схема:** впервые проценты меньше суммы "
            "погашения основного долга в "
            f"**{credit_month_description(first_principal_dominant_month)}**."
        )
    else:
        st.write(
            f"**{scheme_name} схема:** за срок кредита проценты "
            "не становятся меньше суммы погашения основного долга."
        )

# ==================================================
# СОХРАНЕНИЕ ИТОГОВОГО РАЗДЕЛА И ВСЕГО ОТЧЁТА
# ==================================================
summary_rows = [
    {'Схема': 'Аннуитетная', 'Переплата, ₽': annuity_result['overpayment'], 'Переплата, %': f'{annuity_overpayment_percent:.2f}%'},
    {'Схема': 'Дифференцированная', 'Переплата, ₽': diff_result['overpayment'], 'Переплата, %': f'{diff_overpayment_percent:.2f}%'},
]
summary_details = []
if first_lower_diff_month is not None:
    summary_details.append('Дифференцированный платёж впервые меньше аннуитетного: ' + credit_month_description(first_lower_diff_month) + '.')
else:
    summary_details.append('Дифференцированный платёж за срок кредита не становится меньше аннуитетного.')
for scheme_name, schedule in credit_schemes.items():
    first_month = next((int(row['Месяц']) for row in schedule if row['Проценты'] < row['Основной долг'] - 1e-8), None)
    summary_details.append(
        scheme_name + ': проценты впервые меньше погашения основного долга — '
        + (credit_month_description(first_month) if first_month is not None else 'за срок кредита такого месяца нет') + '.'
    )
real_summary_rows = [
    {'Схема': name, 'Приведённая переплата, ₽': real_overpayments[name],
     'Приведённая переплата, %': f'{real_overpayments[name] / amount * 100:.2f}%'}
    for name in ('Аннуитетная', 'Дифференцированная')
]
section_6 = (
    '<h3>Номинальная переплата по кредиту</h3>' + report_table(pd.DataFrame(summary_rows))
    + '<h3>Переплата по кредиту с учётом инфляции</h3>'
    + report_table(pd.DataFrame(real_summary_rows))
    + '<p>Приведённая переплата — сумма дисконтированных платежей минус первоначальная сумма кредита; не является фактическими процентами банку.</p>' 
    + '<p>' + escape(summary_details[0]) + '</p>'
    + ''.join('<p>' + escape(line) + '</p>' for line in summary_details[1:])
)
save_section_button(6, 'Итоги расчёта', report_add('6', 'Итоги расчёта', section_6))

st.divider()
st.subheader('Сохранить весь отчёт')
st.caption('Без галочек сохраняется полный отчёт. При выборе галочек сохраняются отмеченные элементы. HTML можно распечатать или сохранить в PDF из браузера.')
st.download_button(
    '📥 Скачать полный отчёт',
    data=report_document(report_selected_sections()),
    file_name='kredit_polnyi_otchet.html',
    mime='text/html',
    type='primary',
    key='download_full_report',
)
