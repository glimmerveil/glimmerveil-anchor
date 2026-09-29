import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as S


LEGACY = "llama_load_print: offloaded 16/28 layers to GPU"
CURRENT = "load_tensors: layer 13 assigned to device Vulkan0\nload_tensors: layer 28 assigned to device Vulkan0"
CPU_ONLY = "load_tensors: layer 13 assigned to device CPU\nload_tensors: layer 28 assigned to device CPU"

assert S._gpu_load_engaged(LEGACY)
assert S._gpu_load_engaged(CURRENT)
assert not S._gpu_load_engaged(CPU_ONLY)

print("✅ RUNG 1 GREEN — legacy and current Vulkan evidence are recognized; CPU-only is rejected")
