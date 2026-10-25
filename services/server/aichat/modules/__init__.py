"""模块包。跨模块接口约定：只 import 其他模块的 service（或 models），
绝不 import 其他模块的 router；异步集成一律走 core.outbox。见 contracts/PROTOCOL.md §9。
"""
