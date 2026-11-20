# 接口

`POST /api/run`：JSON中的csv文本，省略使用样例；或multipart字段file。最大5MB。

`POST /api/m1`至`POST /api/m8`：独立运行到指定模块，JSON结构同运行接口。M8为多过境融合确认：只产出融合提案（融合段含来源场景、行号、版本、采集时间）与未融合原因，不改变M4–M6的基线结果。

`GET /api/history`：历史批次（含fusion_status）。`POST /api/review`接收id、revision和decision（通过或退回）。`GET /api/evidence.csv`提供单一证据导出，融合批次追加“8-未融合”与“融合采购台账”两类行。

`POST /api/fusion/confirm`：融合确认接口，接收id、revision、decision（`已确认`或`已退回`）。确认后在同一事务内重算融合口径的缺口与采购，写入采购台账并保存confirmed视图；退回则保留基线。revision乐观锁，陈旧提交409；已确认/已退回批次不可重复确认（409，code=`FUSION_STATE`）；重算中断整体回滚，旧版完整保留（500，code=`INTERNAL`）。同一批次重复提交不会新增采购（台账以run_id+场景为唯一键）。

`GET /api/fusion/ledger?run_id=`：采购台账，每个场景仅一条，内嵌该场景全部来源观测（场景/版本/采集时间/行号/角色/段宽）。`GET /api/fusion/sample`：多过境融合演示CSV。

结构错误422，版本变化409，文件过大413；错误返回code与message。所有页面可从左侧八个模块入口访问。

`GET /api/runs/<id>`读取指定批次（确认后含confirmed对象与fusion_status）；页面与证据CSV通过run_id查询参数绑定批次，模块导航保留该参数。

JSON请求体必须是对象，数组、标量、null、损坏JSON及错误上传字段返回400，且不运行默认样例。
