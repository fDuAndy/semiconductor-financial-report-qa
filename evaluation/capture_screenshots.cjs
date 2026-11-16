const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const outputDirectory = path.join(__dirname, "screenshots");
const cases = [
  {
    name: "Q01_中芯收入证据.png",
    question: "中芯国际2025年营业收入是多少？换算为亿元并指出原表单位。",
    expected: "中芯国际"
  },
  {
    name: "Q08_未来年度拒答.png",
    question: "根据2025年年报，给出上述10家公司2027年已经实现的营业收入。",
    expected: "无法提供之后年度已经实现的收入"
  },
  {
    name: "Q09_全景覆盖与限制.png",
    question: "逐家汇总10家公司2025年营业收入和产业链环节；保留年报披露币种，并指出哪些金额不能直接排名。",
    expected: "已覆盖10家公司"
  }
];

async function main() {
  fs.mkdirSync(outputDirectory, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 });
  try {
    for (const item of cases) {
      await page.goto("http://127.0.0.1:8765", { waitUntil: "networkidle" });
      await page.locator("#question").fill(item.question);
      await page.getByRole("button", { name: "提问并查看出处" }).click();
      await page.waitForFunction((expected) => document.querySelector("#results")?.innerText.includes(expected), item.expected);
      await page.screenshot({ path: path.join(outputDirectory, item.name), fullPage: false });
      process.stdout.write(`Captured ${item.name}\n`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
