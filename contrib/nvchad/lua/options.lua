require "nvchad.options"

local o = vim.o

-- Relative line numbers make jump distances readable (5j, 12k, etc.)
o.relativenumber = true

-- Keep context lines above/below cursor — prevents editing at screen edge
o.scrolloff     = 8
o.sidescrolloff = 8

-- No soft-wrap: Terraform, YAML, and Go lines should not wrap visually
o.wrap = false

-- Prompt on :q with unsaved changes instead of erroring
o.confirm = true
