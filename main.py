import uvicorn


def main():
    uvicorn.run("app.main:app", reload=True, port=8000)


if __name__ == "__main__":
    main()
