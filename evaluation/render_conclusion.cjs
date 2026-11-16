const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1240, height: 1754 }, deviceScaleFactor: 1 });
    await page.goto("file:///C:/Users/86185/Desktop/word-test/semiconductor_kb/evaluation/conclusion.html", { waitUntil: "networkidle" });
    await page.pdf({
      path: path.join(__dirname, "方向A一页结论.pdf"),
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: false
    });
    process.stdout.write("Created one-page assignment conclusion PDF.\n");
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
