import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

fp = '/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf'
try:
    font_manager.fontManager.addfont(fp)
    plt.rcParams['font.family'] = font_manager.FontProperties(fname=fp).get_name()
except Exception:
    for f in font_manager.fontManager.ttflist:
        if 'CJK' in f.name:
            plt.rcParams['font.family'] = f.name; break
plt.rcParams['axes.unicode_minus'] = False

CATS = {
    'AI存储/内存':  ('#dc2626', [('海力士',2),('DRAM(ETF)',3),('MU',0.5)]),
    'AI算力/芯片':  ('#ea580c', [('AMD',1),('MRVL',2),('COHR',0.7)]),
    'AI半导体设备': ('#fb923c', [('TSM',1.4),('AMAT',1)]),
    'AI算力云':     ('#f59e0b', [('NBIS',3.7),('CRWV',1)]),
    '互联网/科技':  ('#0ea5e9', [('GOOG',1),('NOK',1.6)]),
    '新能源车':     ('#16a34a', [('XPEV',4)]),
    '消费':         ('#8b5cf6', [('泡泡玛特',0.5)]),
    '加密/区块链':  ('#64748b', [('BTC',3),('CRCL',3)]),
    '前沿题材':     ('#94a3b8', [('QUBT',0.5),('XE',0.7)]),
    '现金':         ('#cbd5e1', [('现金',1)]),
}

stock_labels, stock_vals, stock_colors = [], [], []
cat_labels, cat_vals, cat_colors = [], [], []
for c,(color,items) in CATS.items():
    s=0
    for name,v in items:
        stock_labels.append(name); stock_vals.append(v); stock_colors.append(color); s+=v
    cat_labels.append(c+'\n('+ '·'.join(n for n,_ in items) +')')
    cat_vals.append(round(s,1)); cat_colors.append(color)

def pct(v, tot): 
    return lambda p: f'{p:.1f}%' if p>=3 else ''

# 个股饼图
fig, ax = plt.subplots(figsize=(8,8))
w,_,at = ax.pie(stock_vals, labels=stock_labels, colors=stock_colors,
    autopct=pct(0,sum(stock_vals)), pctdistance=0.78, startangle=90,
    wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2),
    textprops=dict(fontsize=11))
for t in at: t.set_color('white'); t.set_fontweight('bold'); t.set_fontsize(9.5)
ax.set_title('当前持仓 · 按个股市值占比', fontsize=16, fontweight='bold', pad=18)
plt.tight_layout()
plt.savefig('/data/workspace/YoungStockDaily/reports/pie_stock.png', dpi=150, bbox_inches='tight')
plt.close()

# 大类饼图
fig, ax = plt.subplots(figsize=(9,9))
w,texts,at = ax.pie(cat_vals, labels=cat_labels, colors=cat_colors,
    autopct=pct(0,sum(cat_vals)), pctdistance=0.80, startangle=90,
    wedgeprops=dict(width=0.46, edgecolor='white', linewidth=2),
    textprops=dict(fontsize=10.5))
for t in at: t.set_color('white'); t.set_fontweight('bold'); t.set_fontsize(10)
ax.set_title('当前持仓 · 按领域大类市值占比', fontsize=16, fontweight='bold', pad=18)
plt.tight_layout()
plt.savefig('/data/workspace/YoungStockDaily/reports/pie_category.png', dpi=150, bbox_inches='tight')
plt.close()
print('OK total=', sum(stock_vals))
