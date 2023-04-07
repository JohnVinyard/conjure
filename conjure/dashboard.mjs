document.addEventListener(
  "DOMContentLoaded",
  async () => {
    console.log("READY");

    let offset = "";

    setInterval(() => {
      console.log(`fetching with timestamp ${offset}`);
      fetch(
        "/feed?" +
          new URLSearchParams({
            offset,
          })
      ).then(async (resp) => {
        const data = await resp.json();
        const list = document.getElementById("new");
        data.forEach(({ key, timestamp }) => {
          list.insertAdjacentHTML(
            "afterbegin",
            `<li><a target="_blank" href="/results/${key}">${key}</a></li>`
          );
        });
        if (data.length > 0) {
          offset = data.slice(-1)[0].timestamp;
          console.log(`Updated timestamp to be ${offset}`);
        }
      });
    }, 2500);

    // list the keys
    const results = await fetch("/");
    const data = await results.json();
    const keysList = document.getElementById("keys");
    keysList.innerHTML = "";
    data.forEach((key) => {
      keysList.insertAdjacentHTML(
        "afterbegin",
        `<li><a target="_blank" href="/results/${key}">${key}</a></li>`
      );
    });
  },
  false
);
