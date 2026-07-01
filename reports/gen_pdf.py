# -*- coding: utf-8 -*-
from fpdf import FPDF
from PIL import Image as PILImage

FONT='/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf'
FONTB='/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Bold.otf'
BASE='/data/workspace/YoungStockDaily/reports/'
OUT=BASE+'holdings_analysis_20260701.pdf'

AMBER=(180,83,9); DARK=(31,41,55); MUTED=(148,163,184); RED=(185,28,28)
SLATE=(71,85,105); HEADBG=(241,245,249); GRID=(226,232,240)

class PDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-12); self.set_font('CN','',7.5); self.set_text_color(*MUTED)
        self.cell(0,6,'Young\'s Stock Daily · 个人复盘记录，不构成投资建议  ·  第 %d 页'%self.page_no(),align='C')

pdf=PDF(orientation='P', unit='mm', format='A4')
pdf.add_font('CN','',FONT)
pdf.add_font('CN','B',FONTB)
pdf.set_auto_page_break(True, margin=16)
pdf.set_margins(16,16,16)
CW=pdf.epw  # content width

def h1(txt):
    pdf.set_font('CN','B',20); pdf.set_text_color(15,23,42)
    pdf.multi_cell(0,9,txt); pdf.ln(1)
def h2(txt):
    pdf.ln(2); pdf.set_font('CN','B',14); pdf.set_text_color(*AMBER)
    pdf.multi_cell(0,7,txt); pdf.ln(1)
def body(txt, size=10.5, color=DARK):
    pdf.set_font('CN','',size); pdf.set_text_color(*color)
    pdf.multi_cell(0,5.6,txt); pdf.ln(0.5)
def note(txt):
    pdf.set_font('CN','',8.5); pdf.set_text_color(*MUTED)
    pdf.multi_cell(0,4.6,txt); pdf.ln(0.5)

def img_centered(path, w_mm):
    im=PILImage.open(path); iw,ih=im.size; h=w_mm*ih/iw
    x=pdf.l_margin+(CW-w_mm)/2
    pdf.image(path, x=x, y=pdf.get_y(), w=w_mm)
    pdf.set_y(pdf.get_y()+h+2)

def table(headers, rows, widths):
    # scale widths to content width
    tot=sum(widths); widths=[w/tot*CW for w in widths]
    lh=5.0
    # header
    pdf.set_font('CN','B',8.5)
    def row_height(cells, ws):
        maxlines=1
        for txt,w in zip(cells,ws):
            pdf.set_font_size(8.5)
            n=max(1, len(pdf.multi_cell(w-2,lh,txt,split_only=True)))
            maxlines=max(maxlines,n)
        return maxlines*lh
    # draw header
    pdf.set_fill_color(*HEADBG); pdf.set_draw_color(*GRID); pdf.set_text_color(31,41,55)
    hh=row_height(headers,widths)
    x0=pdf.get_x(); y0=pdf.get_y()
    x=x0
    for txt,w in zip(headers,widths):
        pdf.rect(x,y0,w,hh,'DF'); 
        pdf.set_xy(x+1,y0+ (hh-lh)/2 if False else y0+1)
        pdf.multi_cell(w-2,lh,txt,align='L')
        x+=w; pdf.set_xy(x,y0)
    pdf.set_y(y0+hh)
    # body rows
    pdf.set_font('CN','',8.5)
    for r in rows:
        if pdf.get_y()+row_height(r,widths) > pdf.h - pdf.b_margin:
            pdf.add_page()
        rh=row_height(r,widths)
        x=pdf.l_margin; y=pdf.get_y()
        for txt,w in zip(r,widths):
            pdf.set_draw_color(*GRID)
            pdf.rect(x,y,w,rh)
            pdf.set_xy(x+1,y+1)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(w-2,lh,txt,align='L')
            x+=w; pdf.set_xy(x,y)
        pdf.set_y(y+rh)
    pdf.ln(2)

# ---- Page 1: 封面 + 个股饼图 ----
pdf.add_page()
h1('2026 年中 · 完整持仓分析报告')
note('日期：2026-07-01   |   口径：市值按固定单位换算（w = 万，k = 千）   |   总市值约 31.6w')
pdf.set_font('CN','',8.5); pdf.set_text_color(*RED)
pdf.multi_cell(0,4.6,'声明：本文为个人持仓思考记录，不构成任何投资建议。投资有风险，决策需谨慎。'); pdf.ln(2)
h2('一、当前持仓分布 · 按个股')
img_centered(BASE+'pie_stock.png', 120)
note('注：DRAM 为 Roundhill Memory ETF（美股代码 DRAM），本身已含美光、SK海力士、三星等，与自持 MU/海力士存在成分重叠。')

# 个股明细表（含具体市值）
h2('二、个股持仓明细（具体市值）')
table(['标的','市值','占比','标的','市值','占比'],
 [['XPEV','4w','12.7%','AMD','1w','3.2%'],
  ['NBIS','3.7w','11.7%','AMAT','1w','3.2%'],
  ['BTC','3w','9.5%','GOOG','1w','3.2%'],
  ['CRCL','3w','9.5%','CRWV','1w','3.2%'],
  ['DRAM(ETF)','3w','9.5%','COHR','0.7w','2.2%'],
  ['海力士','2w','6.3%','XE','0.7w','2.2%'],
  ['MRVL','2w','6.3%','泡泡玛特','0.5w','1.6%'],
  ['NOK','1.6w','5.1%','MU','0.5w','1.6%'],
  ['TSM','1.4w','4.4%','QUBT','0.5w','1.6%'],
  ['现金','1w','3.2%','—','—','—']],
 [22,16,14,22,16,14])
note('合计：31.6w（100%）。上表按市值从大到小排列，便于直观查看单票权重。')

# ---- Page 2: 大类饼图 ----
pdf.add_page()
h2('三、当前持仓分布 · 按领域大类')
img_centered(BASE+'pie_category.png', 150)
body('AI 四大主线（存储 + 算力芯片 + 算力云 + 半导体设备）合计约 51.6%，是组合的正确基本盘。')

# ---- Page 3: 大类占比表 ----
pdf.add_page()
h2('四、领域大类占比')
table(['大类','市值','占比','含标的','评价'],
 [['加密/区块链','6w','19.0%','BTC·CRCL','熊市失血，需减'],
  ['AI存储/内存','5.5w','17.4%','海力士·DRAM(ETF)·MU','HBM 超级周期，最强主线'],
  ['AI算力云','4.7w','14.9%','NBIS·CRWV','半年最大赢家，核心持有'],
  ['新能源车','4w','12.7%','XPEV','单票过重，需砍'],
  ['AI算力/芯片','3.7w','11.7%','AMD·MRVL·COHR','赢家阵营，方向正确'],
  ['互联网/科技','2.6w','8.2%','GOOG·NOK','稳健底仓'],
  ['AI半导体设备','2.4w','7.6%','TSM·AMAT','代工/设备龙头'],
  ['前沿题材','1.2w','3.8%','QUBT·XE','消耗仓，可清理'],
  ['现金','1w','3.2%','现金','弹药偏少'],
  ['消费','0.5w','1.6%','泡泡玛特','非核心']],
 [22,10,12,42,32])

h2('五、结构诊断：赢家分散，输家集中')
for p in [
 '组合最大的问题不是"选错方向"，而是仓位配置与判断相互矛盾：',
 '1. XPEV 是全组合最大单票（4w / 12.7%），却是持续下跌的失血标的（YTD -35%），与"早就计划退出新能源车"的判断严重冲突——又一次温水煮青蛙。',
 '2. 加密敞口高达 19%（BTC 3w + CRCL 3w），而 BTC 已跌破熊市生命线（半年 -50%）、CRCL 逻辑崩塌（护城河被 OpenAI USD 冲击），双重承压。',
 '3. 真正的赢家（NBIS、MU、AMD、AMAT）反而仓位偏小或分散，MU 仅 0.5w，没能充分放大主线收益。',
 '4. 存储敞口存在隐性重叠：DRAM(ETF) 3w 内部已含 MU/海力士，叠加单独持有的 MU 0.5w + 海力士 2w，实际存储集中度高于表面。',
 '一句话：该重的（存储/算力赢家）不够重，该砍的（新能源车/加密）反而最重。']:
    body(p)

# ---- Page 4: 分标的 + 总方向 ----
pdf.add_page()
h2('六、分标的调整建议')
table(['标的','主营/逻辑','走势','建议'],
 [['XPEV 小鹏','新能源车，赛道承压','YTD -35%','坚决减/清仓，反弹即走'],
  ['CRCL Circle','稳定币，护城河被侵蚀','-38%(20d)','止损离场，别补仓'],
  ['BTC','加密龙头，跌破熊市生命线','半年 -50%','减至底仓，控制敞口'],
  ['QUBT/XE','量子计算/核能，题材股','趋势向下','清理，腾挪给主线'],
  ['NOK 诺基亚','通信设备，估值偏高','-21%(20d)','观察，走弱可减'],
  ['CRWV CoreWeave','AI云算力，弹性大但亏损','-15%(20d)','小仓持有，控制比例'],
  ['泡泡玛特','潮玩消费，高位回落','-14%(20d)','持有观察，非核心'],
  ['NBIS Nebius','AI算力新贵，最大赢家','+230%','核心持有，回调加仓'],
  ['DRAM(ETF)','Roundhill存储ETF，含MU/海力士','+154%','加仓主力，注意成分重叠'],
  ['MU/海力士','存储，HBM 超级周期','MU +305%','加仓主力，优先回补'],
  ['AMD/TSM/AMAT/MRVL/COHR','算力芯片/设备/光互联','普遍强势','持有，AMAT/COHR 可小加'],
  ['GOOG 谷歌','AI+搜索+云，估值合理','+19%','持有/可加，稳健底仓']],
 [30,50,22,38])

h2('七、调仓总方向')
body('把"赢家分散、输家集中"扭转为"赢家集中、输家出清"。')
for p in [
 '砍：XPEV / CRCL / BTC(部分) / QUBT / XE，合计可释放约 8~10w。',
 '加：集中回补到 存储(MU/海力士，注意与 DRAM ETF 重叠) + AI算力(NBIS/AMD/AMAT) 主线。',
 '留弹药：现金比例可从 3% 提升到 5~8%，用于主线回调时低吸，克服"怕追高"心结——趋势明确时，有纪律的追高不是错。',
 '这是把整体收益从 +22.7% 拉回 +50% 目标的唯一可行路径：用赢家的确定性，覆盖并替换掉输家的失血。']:
    body(p)
pdf.ln(2)
note('数据来源：腾讯自选股接口（个股/ETF 涨跌幅，截至 2026-07-01）、公开市场信息（BTC 走势、DRAM ETF 成分）。')

pdf.output(OUT)
print('PDF OK ->', OUT)
