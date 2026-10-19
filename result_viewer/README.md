# XSkill 实验结果查看工具

只读查看指定实验目录内已有的记录。使用 XSkill 的 Python 3.11 环境和标准库，无新增运行依赖，不调用模型，不写入实验目录。前端使用本地 HTML/CSS/JavaScript，无构建步骤或外部 CDN。

## 启动

在 guoxi-desktop 上执行：

```bash
cd /home/guoxi/Projects/evolving_si/XSkill
uv run --no-sync python result_viewer/server.py \
  --experiment output/agentvista_xskill_train \
  --experiment output/agentvista_xskill_test \
  --port 28765
```

`--experiment` 可重复指定，相对路径相对于启动时的工作目录，也支持绝对路径。实验在页面左侧下拉框切换。`--port` 是远端监听端口，默认 28765。服务监听 0.0.0.0，即所有 IPv4 网络接口，使用 Ctrl-C 停止。

浏览器直接打开 http://10.1.110.29:28765 ，无需 SSH 端口转发。服务提供启动时指定实验的只读访问，没有登录认证。启动前确认所选端口没有被其他服务占用。

## 展示范围

- 实验概览：题目 ID 筛选、每题 rollout 得分、保存的完成状态、数据集原始指标，以及 `reevaluations` 中的评分来源切换。
- 单题过程：题目、原图、标准答案，rollout 的逐轮模型文本、工具参数/返回、关联图片、完整注入 prompt、回答及评价。轨迹中的图片引用匹配到文件名时展示在对应步骤，全部图片也可在 rollout 末尾查看。
- Phase 1：图像分析缓存，轨迹总结的 prompt/response，跨 rollout 批评的 prompt/response 与解析后经验，以及处理后的单题技能文本。
- Phase 2：任务分解和检索记录，按经验 ID 对照改写前后文本，处理后的适配技能。保留完整检索记录入口，便于核对解析展示。
- 知识库快照：`snapshots/batch_*` 与实验自身 `memory_bank` 中的记录；选择两个同类知识文件做文本 diff。batch 快照是处理前状态，memory_bank 是读取时的当前文件，不推断其中的合并来源。测试实验的外部知识库不自动跟随访问，应显式添加对应训练实验。

长文本按需展开，图片延迟加载。Markdown 以保留格式的源文本展示，不执行或渲染记录里的 HTML。未找到文件不代表对应环节没有执行。文件读取错误、部分写入的 JSON 会显示错误；实验仍在运行时可手动刷新。服务不缓存结果，不声称跨文件读取是同一个原子快照。

只允许读取选定目录内的已知产物名称、图像和图像分析缓存；路径穿越和指向目录外的符号链接被拒绝。运行脚本、日志、环境文件不作为接口开放。工具没有写入、重新评分或执行实验的接口。

## 验证

在仓库根目录执行：

```bash
uv run --no-sync python -m unittest discover -s result_viewer -p 'test_*.py'
uv run --no-sync python eval/infer_api.py --help
uv run --no-sync python eval/rejudge.py --help
```

测试使用工具目录下自动清理的独立样例，不写入真实实验或 `/tmp`。Ruff 不在现有项目环境中时，可使用独立工具环境运行，不修改项目依赖：

```bash
uv tool run ruff check result_viewer
uv tool run ruff format --check result_viewer
```
