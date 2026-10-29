/* Mount upstream components without changing their DOM/styles or state logic. */
window.__ModuleLoader__ = {
  load({ factory }) {
    const plugin = factory((id) => {
      if (id === 'react') return window.React;
      throw new Error('Unknown module: ' + id);
    });
    let mounted = false;
    plugin.apply({ slots: {
      inject(name, register) { register(); },
      register(slot, Component) {
        if (slot.name === 'shell.overlay') {
          ReactDOM.createRoot(document.getElementById('overlay')).render(React.createElement(Component));
        } else if (!mounted) {
          mounted = true;
          ReactDOM.createRoot(document.getElementById('settings')).render(React.createElement(Component, {view:'page'}));
        }
      }
    }});
  }
};
