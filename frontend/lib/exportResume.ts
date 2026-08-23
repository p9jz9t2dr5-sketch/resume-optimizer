// Client-only resume export helpers.
// `html-to-image` and `jspdf` are browser-only, so they are dynamically
// imported inside the handlers to avoid touching `window`/`document` during SSR.

function triggerDownload(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/** Capture a DOM node as a high-resolution PNG data URL. */
async function capturePng(node: HTMLElement): Promise<string> {
  const { toPng } = await import("html-to-image");
  return toPng(node, {
    pixelRatio: 2,
    backgroundColor: "#ffffff",
  });
}

/** Render a resume template node into a PNG file and trigger download. */
export async function downloadPng(node: HTMLElement, filename: string) {
  const dataUrl = await capturePng(node);
  triggerDownload(dataUrl, `${filename}.png`);
}

/** Render a resume template node into a multi-page A4 PDF and trigger download. */
export async function downloadPdf(node: HTMLElement, filename: string) {
  const dataUrl = await capturePng(node);
  const { jsPDF } = await import("jspdf");

  const img = await loadImage(dataUrl);
  const imgWidth = img.naturalWidth;
  const imgHeight = img.naturalHeight;

  const pdf = new jsPDF({ orientation: "portrait", unit: "px", format: "a4" });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();

  const scale = pageWidth / imgWidth;
  // Height of a single page expressed in source-image pixels.
  const sliceHeight = Math.floor(pageHeight / scale);

  let cursor = 0;
  let page = 0;
  while (cursor < imgHeight) {
    if (page > 0) pdf.addPage();

    const height = Math.min(sliceHeight, imgHeight - cursor);
    const canvas = document.createElement("canvas");
    canvas.width = imgWidth;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas not supported");

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, cursor, imgWidth, height, 0, 0, imgWidth, height);

    pdf.addImage(canvas.toDataURL("image/png"), "PNG", 0, 0, pageWidth, height * scale);
    cursor += height;
    page++;
  }

  pdf.save(`${filename}.pdf`);
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Failed to load rendered resume image"));
    img.src = src;
  });
}
