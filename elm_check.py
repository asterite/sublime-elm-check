import json
import subprocess
import os
import os.path
import cgi
import _thread

import sublime_plugin
import sublime

class ElmCheckPluginListener(sublime_plugin.EventListener):
  def on_post_save(self, view):
    settings = sublime.load_settings('ElmCheck.sublime-settings')
    if settings.get('elm_check'):
      view.run_command('elm_check')

class ElmCheckCommand(sublime_plugin.TextCommand):
  phantom_sets_by_buffer = {}

  def safe_html(self, string):
    return cgi.escape(string).replace('\n', '<br>').replace(' ', '&nbsp;')

  def is_enabled(self):
    caret = self.view.sel()[0].a
    syntax_name = self.view.scope_name(caret)
    return "source.elm" in syntax_name

  def run(self, edit):
    _thread.start_new_thread( self.doit, (edit,) )

  def doit(self, edit):
    view = self.view
    vsize = view.size()
    region = sublime.Region(0, vsize)
    src = view.substr(region)
    window = view.window()
    buffer_id = view.buffer_id()

    if buffer_id not in self.phantom_sets_by_buffer:
      phantom_set = sublime.PhantomSet(view, "elm_check")
      self.phantom_sets_by_buffer[buffer_id] = phantom_set
    else:
      phantom_set = self.phantom_sets_by_buffer[buffer_id]

    filename = self.view.file_name()
    basename = filename
    dirname = os.path.dirname(basename)
    found_elm_json = True

    while True:
      elm_json = os.path.join(dirname, "elm.json")
      if os.path.exists(elm_json):
        break

      basename = dirname
      dirname = os.path.dirname(basename)
      if dirname == basename:
        found_elm_json = False
        break

    if not found_elm_json:
      return

    filename = filename[len(dirname)+1:]

    settings = sublime.load_settings('ElmCheck.sublime-settings')
    command = [settings.get("elm_check_cmd"), "make", "--report", "json", "--output", "/dev/null", filename]

    # for Windows Subsystem for Linux
    if os.name == "nt": command.insert(0, "wsl")

    proc = subprocess.Popen(args=command, cwd=dirname, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate(src.encode('utf-8'))
    stdout = stdout.decode('utf-8')
    stderr = stderr.decode('utf-8')
    exit = proc.returncode

    if exit == 0:
      self.view.erase_regions('elm_check_errors')
      window.run_command("hide_panel")
      phantom_set.update([])
    else:
      phantoms = []

      plain_text_error = ""

      errors = json.loads(stderr)
      if errors["type"] == "compile-errors":
        for some_errors in errors["errors"]:
          for problem in some_errors["problems"]:
            start_line = problem["region"]["start"]["line"]
            start_column = problem["region"]["start"]["column"]
            end_line = problem["region"]["end"]["line"]
            end_column = problem["region"]["end"]["column"]

            error_message = ""

            for message in problem["message"]:
              if isinstance(message, str):
                error_message += self.safe_html(message)
                plain_text_error += message
              else:
                string = message["string"]
                bold = message["bold"]
                underline = message["underline"]
                color = message["color"]

                error_message += '<span style="'
                if color:
                  error_message += "color: " + color
                error_message += '">'
                error_message += self.safe_html(string)
                error_message += '</span>'

                plain_text_error += string

            region = sublime.Region(
                  view.text_point(start_line - 1, start_column - 1),
                  view.text_point(end_line - 1, end_column - 1)
                )

            phantoms.append(
              sublime.Phantom(
                region,
                ('<div style="font-family:monospace; border:1px solid #660000; background-color:#111111; padding:10px">' +
                    error_message +
                  '</div>'),
                sublime.LAYOUT_BELOW,
              ),
            )

            self.view.add_regions('elm_check_errors', [region], 'comment', 'dot', sublime.DRAW_NO_FILL)

      phantom_set.update(phantoms)

      error_panel = window.create_output_panel('elm_check_errors')
      error_panel.run_command("append", {"characters": plain_text_error})
      window.run_command("show_panel", {"panel": "output.elm_check_errors"})
