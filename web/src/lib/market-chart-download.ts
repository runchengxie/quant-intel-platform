type ChartKind = 'market-daily' | 'asia-daily';

export async function downloadMarketChartPng(svg: SVGElement, date: string, kind: ChartKind = 'market-daily'): Promise<void> {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('无效报告日期');
  if (!['market-daily', 'asia-daily'].includes(kind)) throw new Error('无效报告类型');
  const width = Number(svg?.getAttribute('width'));
  const height = Number(svg?.getAttribute('height'));
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error('图表尺寸不可用');
  }
  const scale = Math.min(2, 8192 / width, 8192 / height, Math.sqrt(12_000_000 / (width * height)));
  const markup = new XMLSerializer().serializeToString(svg);
  const sourceUrl = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const picture = new Image();
    await new Promise((resolve, reject) => {
      picture.onload = resolve;
      picture.onerror = () => reject(new Error('图表图片加载失败'));
      picture.src = sourceUrl;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('浏览器不支持图表导出');
    context.scale(scale, scale);
    context.drawImage(picture, 0, 0, width, height);
    const png = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('PNG 生成失败')), 'image/png');
    });
    const downloadUrl = URL.createObjectURL(png);
    try {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${date}-${kind}-report.png`;
      try {
        document.body.append(link);
        link.click();
      } finally {
        link.remove();
      }
    } finally {
      setTimeout(() => URL.revokeObjectURL(downloadUrl), 60_000);
    }
  } finally {
    URL.revokeObjectURL(sourceUrl);
  }
}
