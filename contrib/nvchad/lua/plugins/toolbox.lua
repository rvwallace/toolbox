return {
  {
    "folke/noice.nvim",
    event = "VeryLazy",
    dependencies = {
      "MunifTanjim/nui.nvim",
    },
    opts = {
      cmdline = {
        enabled = true,
        view = "cmdline_popup",
      },
      messages = {
        enabled = false,
      },
      popupmenu = {
        enabled = true,
        backend = "nui",
      },
      notify = {
        enabled = false,
      },
      lsp = {
        progress = { enabled = false },
        hover = { enabled = false },
        signature = { enabled = false },
      },
      presets = {
        command_palette = true,
      },
    },
  },
}
