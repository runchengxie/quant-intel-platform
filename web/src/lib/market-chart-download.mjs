export async function downloadMarketChartPng(svg, date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('无效报告日期');
  const width = Number(svg?.getAttribute('width'));
  const height = Number(svg?.getAttribute('height'));
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error('图表尺寸不可用');
  }
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
    canvas.width = width * 2;
    canvas.height = height * 2;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('浏览器不支持图表导出');
    context.scale(2, 2);
    context.drawImage(picture, 0, 0, width, height);
    const png = await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('PNG 生成失败')), 'image/png');
    });
    const downloadUrl = URL.createObjectURL(png);
    try {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${date}-market-daily-charts.png`;
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
