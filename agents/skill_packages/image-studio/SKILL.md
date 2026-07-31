---
name: image-studio
description: 通过混元或已配置的后备提供商生成图片、参考图生图并连续修改。
---

# Image Studio

生成新图片或修改图片时设置 `needs_image_generation`。现实主体需要外观准确且用户没有参考图时，才同时使用搜索和图片审核；纯幻想、抽象画面或已有附图时不搜索。

生成结果必须先写入当前用户的 Makers Blob 前缀，再发布给图片组件；不得暴露其他用户的存储键。
