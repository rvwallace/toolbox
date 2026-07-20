return {
  {
    "xiyaowong/transparent.nvim",
    lazy = false, -- or true if you want to lazy-load on some event
    opts = {
      -- optional: see plugin readme for these
      extra_groups = {
        "NormalFloat",
        "NvimTreeNormal",
        "TelescopeNormal",
        "TelescopeBorder",
      },
      exclude_groups = {}, -- groups you do NOT want to clear
    },
    config = function(_, opts)
      require("transparent").setup(opts)
      -- optional: start enabled
      -- require("transparent").enable()

      -- <leader>ut to toggle transparency
      vim.keymap.set("n", "<leader>ut", "<cmd>TransparentToggle<cr>", { desc = "Toggle transparency" })
    end,
  },
}
