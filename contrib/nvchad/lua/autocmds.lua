require "nvchad.autocmds"

local autocmd = vim.api.nvim_create_autocmd

-- Terraform / HCL: community standard is 2-space indent
autocmd("FileType", {
  pattern = { "terraform", "hcl" },
  callback = function()
    vim.opt_local.tabstop = 2
    vim.opt_local.shiftwidth = 2
    vim.opt_local.expandtab = true
  end,
})

-- YAML / Ansible: 2-space indent
autocmd("FileType", {
  pattern = { "yaml", "yaml.ansible" },
  callback = function()
    vim.opt_local.tabstop = 2
    vim.opt_local.shiftwidth = 2
    vim.opt_local.expandtab = true
  end,
})

-- Go: gofmt uses real tabs — keep expandtab off
autocmd("FileType", {
  pattern = { "go" },
  callback = function()
    vim.opt_local.tabstop = 4
    vim.opt_local.shiftwidth = 4
    vim.opt_local.expandtab = false
  end,
})

-- Relative numbers in normal mode, absolute in insert mode
autocmd("InsertEnter", {
  callback = function()
    vim.wo.relativenumber = false
  end,
})
autocmd("InsertLeave", {
  callback = function()
    vim.wo.relativenumber = true
  end,
})

-- Highlight yanked text briefly (works with any colorscheme)
autocmd("TextYankPost", {
  callback = function()
    vim.highlight.on_yank { higroup = "Visual", timeout = 200 }
  end,
})

-- Auto-reload files changed outside Neovim.
-- FocusGained catches returning to the terminal; BufEnter catches switching
-- to a buffer that was already open but stale.
autocmd({ "FocusGained", "BufEnter" }, {
  callback = function()
    -- Skip if we're inside the command-line window (checktime errors there)
    if vim.fn.getcmdwintype() == "" then
      vim.cmd "checktime"
    end
  end,
})

-- FileChangedShellPost fires after Neovim silently reloads a buffer from disk.
-- (When the buffer has unsaved changes Neovim prompts natively — no need to
-- duplicate that logic here.)
autocmd("FileChangedShellPost", {
  callback = function()
    vim.notify(
      ("Reloaded from disk: %s"):format(vim.fn.expand "<afile>:t"),
      vim.log.levels.INFO
    )
  end,
})

-- Reopen Nvdash after the final file buffer is deleted.
autocmd("BufDelete", {
  callback = function()
    local bufs = vim.t.bufs or {}
    if not vim.g.nvdash_displayed and #bufs == 1 and vim.api.nvim_buf_get_name(bufs[1]) == "" then
      vim.cmd "Nvdash"
    end
  end,
})
