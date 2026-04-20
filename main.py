import uvicorn


def main():
    uvicorn.run("app.main:app", reload=True, port=6767)


if __name__ == "__main__":
    main()
