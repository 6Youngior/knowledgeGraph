# Beamer 主题

采用 [sonnyhcl/beamerthemefdu](https://github.com/sonnyhcl/beamerthemefdu)，非官方复旦大学 Beamer 主题，Apache-2.0。

vendor-fdu/ 保留上游主题、README 和许可证。主题文件 SHA-256：

    493e458ec6cd955da6567c613374d2cc1faf25c51e7e21a1e5a959ddeabfa3d3

main.tex 通过原生 FDU 主题提供封面、蓝色标题栏、章节导航、三段页脚和校徽水印，没有重新定义这些模板。内容使用标准 Beamer block、表格和 TikZ 图。

本地配置包括参考配色、字体、字号、水印透明度 0.022，以及页脚去除单位字段。上游 .sty 文件保持原样。封面作者和 PDF author 字段为空，页脚短作者字段用于显示项目名 FinGraph。

resources/fudan.pdf 与 resources/background.pdf 为主题随附的校名、校徽资源，版权归复旦大学，用于本课程汇报。
