REASONS = {"COLUMNS":"列数不符", "HEADER":"字段缺失", "MISSING":"必填值为空", "NUMBER":"数值无效", "RANGE":"超出范围", "DUPLICATE":"相同行重复", "CONFLICT":"同键数值冲突", "VERSION":"版本冲突", "EMPTY":"输入为空", "STRUCTURE":"文件结构错误", "FUSE_SUPERSEDED":"旧版本，清晰段已被最新过境覆盖", "FUSE_REDUNDANT":"清晰段与已融合覆盖完全重叠", "FUSE_CLOUD":"目标纬带内无清晰段", "FUSE_QUALITY":"影像质量未通过", "FUSE_BASELINE":"最新过境，已作为基线采信"}
def isolate(ctx, row, code, detail):
    ctx['quarantine'].append({**row, '原因码': code, '原因': detail})
